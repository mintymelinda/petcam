#include <liveMedia.hh>
#include <BasicUsageEnvironment.hh>
#include <GroupsockHelper.hh>
#include <algorithm>
#include <cstdint>
#include <cstring>
#include <condition_variable>
#include <deque>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

namespace {
constexpr std::size_t kMaxNal = 16U * 1024U * 1024U;
constexpr std::size_t kMaxQueue = 64U * 1024U * 1024U;
struct Nal { std::uint64_t seq; std::vector<unsigned char> data; bool key; };
std::mutex queueMutex, lifecycleMutex;
std::deque<Nal> queue;
std::size_t queueBytes = 0;
std::uint64_t sequence = 1;
std::thread worker;
TaskScheduler* scheduler = nullptr;
EventTriggerId shutdownId = 0;
char watch = 0;
bool startupDone = false;
std::condition_variable startupCondition;
int startupCode = -1;
std::string startupMessage;

class NalSource final : public FramedSource {
public:
  static NalSource* createNew(UsageEnvironment& env) { return new NalSource(env); }
protected:
  explicit NalSource(UsageEnvironment& env) : FramedSource(env) {}
  void doGetNextFrame() override { deliver(); }
  void doStopGettingFrames() override {
    if (nextTask() != nullptr) envir().taskScheduler().unscheduleDelayedTask(nextTask());
  }
private:
  static void retry(void* p) { static_cast<NalSource*>(p)->deliver(); }
  void deliver() {
    if (!isCurrentlyAwaitingData()) return;
    std::vector<unsigned char> data;
    {
      std::lock_guard<std::mutex> lock(queueMutex);
      if (!queue.empty()) {
        if (!cursorSet_) {
          for (auto it = queue.rbegin(); it != queue.rend(); ++it)
            if (it->key) { cursor_ = it->seq; cursorSet_ = true; break; }
        }
        if (cursorSet_) {
          if (cursor_ < queue.front().seq) cursorSet_ = false;
          else {
            auto it = std::find_if(queue.begin(), queue.end(),
              [this](const Nal& n) { return n.seq >= cursor_; });
            if (it != queue.end()) {
              if (it->seq != cursor_) {
                it = std::find_if(it, queue.end(), [](const Nal& n) { return n.key; });
                if (it == queue.end()) cursorSet_ = false;
              }
              if (cursorSet_ && it != queue.end()) {
                data = it->data;
                cursor_ = it->seq + 1;
              }
            }
          }
        }
      }
    }
    if (data.empty()) {
      nextTask() = envir().taskScheduler().scheduleDelayedTask(5000, retry, this);
      return;
    }
    fFrameSize = static_cast<unsigned>(std::min<std::size_t>(data.size(), fMaxSize));
    fNumTruncatedBytes = static_cast<unsigned>(data.size() - fFrameSize);
    std::memcpy(fTo, data.data(), fFrameSize);
    gettimeofday(&fPresentationTime, nullptr);
    fDurationInMicroseconds = 0;
    FramedSource::afterGetting(this);
  }
  std::uint64_t cursor_ = 0;
  bool cursorSet_ = false;
};

class H264Subsession final : public OnDemandServerMediaSubsession {
public:
  static H264Subsession* createNew(UsageEnvironment& env) { return new H264Subsession(env); }
protected:
  explicit H264Subsession(UsageEnvironment& env) : OnDemandServerMediaSubsession(env, False) {}
  FramedSource* createNewStreamSource(unsigned, unsigned& bitrate) override {
    bitrate = 8000;
    return NalSource::createNew(envir());
  }
  RTPSink* createNewRTPSink(Groupsock* groupsock, unsigned char payload, FramedSource*) override {
    return H264VideoRTPSink::createNew(envir(), groupsock, payload);
  }
private:
  ~H264Subsession() override = default;
};
void stopEvent(void*) { watch = 1; }

void serve(unsigned short port, std::string path) {
  TaskScheduler* localScheduler = BasicTaskScheduler::createNew();
  UsageEnvironment* env = BasicUsageEnvironment::createNew(*localScheduler);
  RTSPServer* server = env ? RTSPServer::createNew(*env, Port(port), nullptr) : nullptr;
  ServerMediaSession* session = nullptr;
  if (server) {
    while (!path.empty() && path.front() == '/') path.erase(path.begin());
    if (path.empty()) path = "petcam";
    session = ServerMediaSession::createNew(*env, path.c_str(), "PetCam",
      "Native H.264 camera stream", True);
    if (session) {
      session->addSubsession(H264Subsession::createNew(*env));
      server->addServerMediaSession(session);
    }
  }
  {
    std::lock_guard<std::mutex> lock(lifecycleMutex);
    scheduler = localScheduler;
    shutdownId = localScheduler->createEventTrigger(stopEvent);
    startupCode = (server && session) ? 0 : -1;
    startupMessage = startupCode == 0 ? "" : (env ? env->getResultMsg() : "Live555 environment creation failed");
    startupDone = true;
  }
  startupCondition.notify_all();
  if (startupCode == 0) {
    watch = 0;
    localScheduler->doEventLoop(&watch);
  }
  if (server) {
    if (session) server->deleteServerMediaSession(session);
    Medium::close(server);
  }
  if (env) env->reclaim();
  delete localScheduler;
  {
    std::lock_guard<std::mutex> lock(lifecycleMutex);
    scheduler = nullptr;
    shutdownId = 0;
  }
}
}

extern "C" {
int petcam_start(unsigned short port, const char* path) {
  std::unique_lock<std::mutex> lock(lifecycleMutex);
  if (worker.joinable()) return -1;
  startupDone = false;
  startupCode = -1;
  startupMessage.clear();
  worker = std::thread(serve, port, path ? path : "/petcam");
  startupCondition.wait_for(lock, std::chrono::seconds(5), [] { return startupDone; });
  if (!startupDone) {
    startupMessage = "Timed out waiting for Live555 startup";
    return -1;
  }
  return startupCode;
}
int petcam_push_nal(const unsigned char* data, std::size_t size, int keyframe) {
  if (!data || size == 0 || size > kMaxNal) return -1;
  Nal item{0, std::vector<unsigned char>(data, data + size), keyframe != 0};
  std::lock_guard<std::mutex> lock(queueMutex);
  item.seq = sequence++;
  queueBytes += item.data.size();
  queue.push_back(std::move(item));
  while (!queue.empty() && (queueBytes > kMaxQueue || queue.size() > 8192)) {
    queueBytes -= queue.front().data.size();
    queue.pop_front();
  }
  return 0;
}
const char* petcam_last_error() { return startupMessage.c_str(); }
void petcam_stop() {
  {
    std::lock_guard<std::mutex> lock(lifecycleMutex);
    if (scheduler && shutdownId) scheduler->triggerEvent(shutdownId, nullptr);
  }
  if (worker.joinable()) worker.join();
  std::lock_guard<std::mutex> lock(queueMutex);
  queue.clear();
  queueBytes = 0;
  sequence = 1;
}
}
