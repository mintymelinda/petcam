c o n s t i m a g e=d o c u m e n t.g e t E l e m e n t B y I d("stream"), s t a t u s=d o c u m e n t.g e t E l e m e n t B y I d("status");
i m a g e.o n l o a d=()=> {
  i m a g e.d a t a s e t.r e a d y="1";
  s t a t u s.h i d d e n=t r u e
};
i m a g e.o n e r r o r=()=> {
  i m a g e.r e m o v e A t t r i b u t e("data-ready");
  s t a t u s.h i d d e n=f a l s e;
  s t a t u s.t e x t C o n t e n t="Camera stream unavailable. Check that the camera is running and MJPEG mode is enabled. Retrying...";
  s e t T i m e o u t(()=> {
    i m a g e.s r c="/stream?retry="+D a t e.n o w()
  }, 3 0 0 0)
}
