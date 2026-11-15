c o n s t $=i d=>d o c u m e n t.g e t E l e m e n t B y I d(i d);
l e t i n v e n t o r y=[], a c t i v e C o n f i g=n u l l, c a p t u r e S t a t u s= {
}, r t m p S e t t i n g s= {
  e n a b l e d:f a l s e
};
$("first-run-form").o n s u b m i t=a s y n c e v e n t=> {
  e v e n t.p r e v e n t D e f a u l t();
  c o n s t p a s s w o r d=$("setup-password").v a l u e, c o n f i r m a t i o n=$("setup-password-confirm").v a l u e, m e s s a g e=$("setup-message"), b u t t o n=$("setup-submit");
  i f(p a s s w o r d!==c o n f i r m a t i o n) {
    m e s s a g e.t e x t C o n t e n t="The passwords do not match.";
    r e t u r n
  }
  b u t t o n.d i s a b l e d=t r u e;
  m e s s a g e.t e x t C o n t e n t="Creating administrator account…";
  t r y {
    c o n s t r e s p o n s e=a w a i t f e t c h("/api/setup",  {
      m e t h o d:"POST", h e a d e r s: {
        "Content-Type":"application/json"
      }, b o d y:J S O N.s t r i n g i f y( {
        p a s s w o r d, p a s s w o r d _ c o n f i r m a t i o n:c o n f i r m a t i o n
      })
    });
    c o n s t d a t a=a w a i t r e s p o n s e.j s o n();
    i f(!r e s p o n s e.o k)t h r o w E r r o r(d a t a.e r r o r||"Initial setup failed");
    m e s s a g e.t e x t C o n t e n t="Administrator account created. Opening PetCam…";
    l o c a t i o n.r e l o a d()
  }
  c a t c h(e r r o r) {
    m e s s a g e.t e x t C o n t e n t=e r r o r.m e s s a g e;
    b u t t o n.d i s a b l e d=f a l s e
  }
};
l e t c s r f T o k e n=n u l l;
l e t l o g i n P r o m i s e=n u l l;
a s y n c f u n c t i o n l o g i n() {
  i f(l o g i n P r o m i s e)r e t u r n l o g i n P r o m i s e;
  l o g i n P r o m i s e=(a s y n c()=> {
    c o n s t s e t u p R e s p o n s e=a w a i t f e t c h("/api/setup/status",  {
      c a c h e:"no-store"
    });
    c o n s t s e t u p S t a t e=a w a i t s e t u p R e s p o n s e.j s o n();
    i f(!s e t u p R e s p o n s e.o k)t h r o w E r r o r(s e t u p S t a t e.e r r o r||"Unable to check initial setup");
    i f(!s e t u p S t a t e.c o n f i g u r e d)t h r o w E r r o r("Create the administrator password in the welcome panel before signing in.");
    r e t u r n a w a i t n e w P r o m i s e((r e s o l v e, r e j e c t)=> {
      c o n s t d i a l o g=$("login-dialog"), f o r m=$("login-form"), p a s s w o r d=$("login-password"), m e s s a g e=$("login-message"), b u t t o n=$("login-submit");
      l e t s e t t l e d=f a l s e;
      c o n s t f i n i s h=(e r r o r, d a t a)=> {
        i f(s e t t l e d)r e t u r n;
        s e t t l e d=t r u e;
        p a s s w o r d.v a l u e="";
        d i a l o g.c l o s e();
        i f(e r r o r)r e j e c t(e r r o r);
        e l s e r e s o l v e(d a t a)
      };
      f o r m.o n s u b m i t=a s y n c e v e n t=> {
        e v e n t.p r e v e n t D e f a u l t();
        b u t t o n.d i s a b l e d=t r u e;
        m e s s a g e.t e x t C o n t e n t="Signing in…";
        t r y {
          c o n s t r e s p o n s e=a w a i t f e t c h("/api/login",  {
            m e t h o d:"POST", h e a d e r s: {
              "Content-Type":"application/json"
            }, b o d y:J S O N.s t r i n g i f y( {
              p a s s w o r d:p a s s w o r d.v a l u e
            })
          });
          c o n s t d a t a=a w a i t r e s p o n s e.j s o n();
          i f(!r e s p o n s e.o k)t h r o w E r r o r(d a t a.e r r o r||"Sign-in failed");
          c s r f T o k e n=d a t a.c s r f _ t o k e n;
          f i n i s h(n u l l, d a t a)
        }
        c a t c h(e r r o r) {
          m e s s a g e.t e x t C o n t e n t=e r r o r.m e s s a g e;
          p a s s w o r d.v a l u e="";
          p a s s w o r d.f o c u s();
          b u t t o n.d i s a b l e d=f a l s e
        }
      };
      d i a l o g.o n c a n c e l=e v e n t=> {
        e v e n t.p r e v e n t D e f a u l t();
        f i n i s h(E r r o r("Sign-in cancelled"))
      };
      p a s s w o r d.s e t A t t r i b u t e("type", "password");
      p a s s w o r d.t y p e="password";
      p a s s w o r d.s e t A t t r i b u t e("autocomplete", "current-password");
      d i a l o g.s h o w M o d a l();
      p a s s w o r d.f o c u s()
    })
  })();
  t r y {
    r e t u r n a w a i t l o g i n P r o m i s e
  }
  f i n a l l y {
    l o g i n P r o m i s e=n u l l
  }
}
a s y n c f u n c t i o n r e q u e s t(p a t h, o p t i o n s= {
}) {
  c o n s t h e a d e r s=n e w H e a d e r s(o p t i o n s.h e a d e r s|| {
  });
  i f(o p t i o n s.m e t h o d&&o p t i o n s.m e t h o d.t o U p p e r C a s e()!=="GET"&&!c s r f T o k e n) {
    l e t s e s s i o n=a w a i t f e t c h("/api/session");
    i f(s e s s i o n.s t a t u s===4 0 1) {
      a w a i t l o g i n()
    }
    e l s e {
      c o n s t s t a t e=a w a i t s e s s i o n.j s o n();
      i f(!s e s s i o n.o k)t h r o w E r r o r(s t a t e.e r r o r||s e s s i o n.s t a t u s T e x t);
      c s r f T o k e n=s t a t e.c s r f _ t o k e n
    }
  }
  i f(o p t i o n s.m e t h o d&&o p t i o n s.m e t h o d.t o U p p e r C a s e()!=="GET"&&c s r f T o k e n)h e a d e r s.s e t("X-PetCam-CSRF", c s r f T o k e n);
  l e t r=a w a i t f e t c h(p a t h,  {
    ...o p t i o n s, h e a d e r s
  });
  i f(r.s t a t u s===4 0 1) {
    a w a i t l o g i n();
    i f(o p t i o n s.m e t h o d&&o p t i o n s.m e t h o d.t o U p p e r C a s e()!=="GET"&&c s r f T o k e n)h e a d e r s.s e t("X-PetCam-CSRF", c s r f T o k e n);
    r=a w a i t f e t c h(p a t h,  {
      ...o p t i o n s, h e a d e r s
    })
  }
  c o n s t d=a w a i t r.j s o n();
  i f(!r.o k)t h r o w E r r o r(d.e r r o r||r.s t a t u s T e x t);
  r e t u r n d
}
c o n s t t a b B u t t o n s=[...d o c u m e n t.q u e r y S e l e c t o r A l l("[data-tab]")];
f u n c t i o n a c t i v a t e T a b(n a m e, m o v e F o c u s=f a l s e) {
  c o n s t s e l e c t e d=t a b B u t t o n s.f i n d(b u t t o n=>b u t t o n.d a t a s e t.t a b===n a m e);
  i f(!s e l e c t e d)r e t u r n;
  f o r(c o n s t b u t t o n o f t a b B u t t o n s) {
    c o n s t a c t i v e=b u t t o n===s e l e c t e d;
    b u t t o n.s e t A t t r i b u t e("aria-selected", S t r i n g(a c t i v e));
    b u t t o n.t a b I n d e x=a c t i v e?0:-1;
    c o n s t p a n e l=$(b u t t o n.g e t A t t r i b u t e("aria-controls"));
    p a n e l.h i d d e n=!a c t i v e;
    p a n e l.c l a s s L i s t.t o g g l e("active", a c t i v e);
  }
  i f(m o v e F o c u s)s e l e c t e d.f o c u s();
}
f o r(c o n s t b u t t o n o f t a b B u t t o n s) {
  b u t t o n.a d d E v e n t L i s t e n e r("click", ()=>a c t i v a t e T a b(b u t t o n.d a t a s e t.t a b));
  b u t t o n.a d d E v e n t L i s t e n e r("keydown", e v e n t=> {
    c o n s t i n d e x=t a b B u t t o n s.i n d e x O f(b u t t o n);
    l e t n e x t=n u l l;
    i f(e v e n t.k e y==="ArrowRight")n e x t=(i n d e x+1)%t a b B u t t o n s.l e n g t h;
    e l s e i f(e v e n t.k e y==="ArrowLeft")n e x t=(i n d e x-1+t a b B u t t o n s.l e n g t h)%t a b B u t t o n s.l e n g t h;
    e l s e i f(e v e n t.k e y==="Home")n e x t=0;
    e l s e i f(e v e n t.k e y==="End")n e x t=t a b B u t t o n s.l e n g t h-1;
    i f(n e x t!==n u l l) {
      e v e n t.p r e v e n t D e f a u l t();
      a c t i v a t e T a b(t a b B u t t o n s[n e x t].d a t a s e t.t a b, t r u e)
    }
  });
}
a c t i v a t e T a b("camera");
r e f r e s h R T M P();
f u n c t i o n m o d e s F o r(c a m e r a) {
  r e t u r n c a m e r a.k i n d==="usb"?c a m e r a.m o d e s.f i l t e r(m=>["MJPG", "MJPEG", "JPEG", "YUYV", "YVYU", "UYVY", "YUV420", "YVU420", "RGB565", "RGB24", "GREY", "H264"].i n c l u d e s(m.f o r m a t)):c a m e r a.m o d e s
}
f u n c t i o n s e l e c t e d C a p t u r e M o d e() {
  t r y {
    r e t u r n J S O N.p a r s e($("mode").v a l u e)
  }
  c a t c h(e r r o r) {
    r e t u r n n u l l
  }
}
f u n c t i o n h 2 6 4 M o d e S e l e c t e d O r A c t i v e() {
  r e t u r n(a c t i v e C o n f i g?.S O U R C E==="usb"&&a c t i v e C o n f i g?.F O R M A T==="H264")||c a p t u r e S t a t u s.a c t i v e _ c a p t u r e _ f o r m a t==="H264"||s e l e c t e d C a p t u r e M o d e()?.f o r m a t==="H264"
}
f u n c t i o n s y n c O u t p u t M o d e C o n t r o l s() {
  c o n s t f o r c e d=h 2 6 4 M o d e S e l e c t e d O r A c t i v e();
  $("rtmp-enabled").c h e c k e d=f o r c e d||!!r t m p S e t t i n g s.e n a b l e d;
  $("rtmp-enabled").d i s a b l e d=f o r c e d;
  $("save-rtmp").d i s a b l e d=f o r c e d;
  d o c u m e n t.q u e r y S e l e c t o r A l l("[data-browser-feed-link]").f o r E a c h(l i n k=> {
    l i n k.c l o s e s t("p").h i d d e n=f o r c e d
  });
  $("h264-mode-note").h i d d e n=!f o r c e d
}
f u n c t i o n p r o j e c t e d P i x e l R a t e(m o d e) {
  r e t u r n m o d e.w i d t h*m o d e.h e i g h t*m o d e.f p s
}
f u n c t i o n e x c e e d s P e r f o r m a n c e B u d g e t(c a m e r a, m o d e) {
  i f(m o d e.f o r m a t==="H264")r e t u r n f a l s e;
  c o n s t b u d g e t=N u m b e r(c a m e r a?.h a r d w a r e _ b u d g e t _ p i x e l s _ p e r _ s e c o n d||0);
  r e t u r n b u d g e t>0&&p r o j e c t e d P i x e l R a t e(m o d e)>b u d g e t
}
f u n c t i o n c o n f i r m P e r f o r m a n c e O v e r r i d e(c a m e r a, m o d e) {
  i f(!e x c e e d s P e r f o r m a n c e B u d g e t(c a m e r a, m o d e))r e t u r n f a l s e;
  c o n s t e s t i m a t e=p r o j e c t e d P i x e l R a t e(m o d e), b u d g e t=N u m b e r(c a m e r a.h a r d w a r e _ b u d g e t _ p i x e l s _ p e r _ s e c o n d);
  r e t u r n c o n f i r m("Performance warning: this capture mode is estimated at "+e s t i m a t e.t o L o c a l e S t r i n g()+" pixels/second, above the "+c a m e r a.h a r d w a r e _ t i e r+" device guideline of "+b u d g e t.t o L o c a l e S t r i n g()+" pixels/second. It may cause low frame rates, dropped frames, or an unresponsive camera stream. Use this mode anyway?")
}
f u n c t i o n s h o w S e l e c t e d M o d e W a r n i n g() {
  c o n s t c=i n v e n t o r y[+$("camera").v a l u e], r a w=$("mode").v a l u e;
  i f(!c||!r a w)r e t u r n;
  c o n s t m o d e=J S O N.p a r s e(r a w);
  i f(e x c e e d s P e r f o r m a n c e B u d g e t(c, m o d e))$("message").t e x t C o n t e n t="Performance warning: this capture mode exceeds the estimated "+c.h a r d w a r e _ t i e r+" device budget. You can still apply it after confirming the warning.";
  e l s e $("message").t e x t C o n t e n t=m o d e.f o r m a t==="H264"?"H.264 selected. The HTTP Browser Source will be disabled and OBS RTSP output will be forced on.":"Selected mode is within the estimated device performance budget.";
  s y n c O u t p u t M o d e C o n t r o l s()
}
f u n c t i o n a c t i v e C a m e r a M a t c h e s(c a m e r a, c o n f i g) {
  i f(!c o n f i g)r e t u r n f a l s e;
  i f(c o n f i g.S O U R C E==="usb")r e t u r n c a m e r a.k i n d==="usb"&&(c o n f i g.U S B _ P H Y S I C A L _ P A T H?c a m e r a.p h y s i c a l _ p a t h===c o n f i g.U S B _ P H Y S I C A L _ P A T H:c a m e r a.d e v i c e===c o n f i g.D E V I C E);
  i f(c o n f i g.S O U R C E==="csi")r e t u r n c a m e r a.k i n d==="csi"&&(c o n f i g.C S I _ D E V I C E _ P A T H?c a m e r a.d e v i c e _ p a t h===c o n f i g.C S I _ D E V I C E _ P A T H:S t r i n g(c a m e r a.c a m e r a)===S t r i n g(c o n f i g.C A M E R A));
  r e t u r n f a l s e
}
f u n c t i o n f i l l M o d e s(p r e f e r r e d=n u l l) {
  c o n s t c=i n v e n t o r y[+$("camera").v a l u e];
  $("mode").r e p l a c e C h i l d r e n();
  i f(!c)r e t u r n;
  l e t m a t c h e d=f a l s e;
  f o r(c o n s t m o f m o d e s F o r(c)) {
    l e t f p s=m.f p s?.l e n g t h?m.f p s:[m.f p s _ r a n g e?.m a x||3 0];
    i f(c.k i n d==="usb")f p s=f p s.f i l t e r(N u m b e r.i s I n t e g e r);
    i f(p r e f e r r e d&&p r e f e r r e d.w i d t h===m.w i d t h&&p r e f e r r e d.h e i g h t===m.h e i g h t&&(p r e f e r r e d.f o r m a t||"CSI")===(m.f o r m a t||"CSI")&&!f p s.s o m e(f=>M a t h.a b s(f-p r e f e r r e d.f p s)<0.1))f p s=[...f p s, p r e f e r r e d.f p s];
    f o r(c o n s t f o f f p s) {
      c o n s t m o d e= {
        f o r m a t:m.f o r m a t||"CSI", w i d t h:m.w i d t h, h e i g h t:m.h e i g h t, f p s:f
      };
      c o n s t o=d o c u m e n t.c r e a t e E l e m e n t("option");
      o.v a l u e=J S O N.s t r i n g i f y(m o d e);
      o.t e x t C o n t e n t=`${m.width}×${m.height} · ${f} fps · ${m.format||"CSI"}`+(e x c e e d s P e r f o r m a n c e B u d g e t(c, m o d e)?" · ⚠ above device estimate":"");
      i f(p r e f e r r e d&&m o d e.w i d t h===p r e f e r r e d.w i d t h&&m o d e.h e i g h t===p r e f e r r e d.h e i g h t&&m o d e.f o r m a t===(p r e f e r r e d.f o r m a t||"CSI")&&M a t h.a b s(m o d e.f p s-p r e f e r r e d.f p s)<0.1) {
        o.s e l e c t e d=t r u e;
        m a t c h e d=t r u e
      }
      $("mode").a p p e n d(o)
    }
  }
  i f(p r e f e r r e d&&!m a t c h e d) {
    c o n s t m o d e= {
      f o r m a t:p r e f e r r e d.f o r m a t||"CSI", w i d t h:p r e f e r r e d.w i d t h, h e i g h t:p r e f e r r e d.h e i g h t, f p s:N u m b e r(p r e f e r r e d.f p s)
    };
    c o n s t o=d o c u m e n t.c r e a t e E l e m e n t("option");
    o.v a l u e=J S O N.s t r i n g i f y(m o d e);
    o.t e x t C o n t e n t=`${mode.width}×${mode.height} · ${mode.fps} fps · ${mode.format} (saved setting; not currently advertised)`;
    o.s e l e c t e d=t r u e;
    $("mode").p r e p e n d(o)
  }
  $("mode").o n c h a n g e=s h o w S e l e c t e d M o d e W a r n i n g;
  s h o w S e l e c t e d M o d e W a r n i n g()
}
f u n c t i o n r e n d e r C a p t u r e S t a t u s() {
  c o n s t f p s=N u m b e r(c a p t u r e S t a t u s.l a t e s t _ c a p t u r e d _ f p s), c o n f i g u r e d=a c t i v e C o n f i g?.F P S, f o r m a t=c a p t u r e S t a t u s.a c t i v e _ c a p t u r e _ f o r m a t;
  i f(N u m b e r.i s F i n i t e(f p s)&&f p s>0) {
    $("capture-rate").t e x t C o n t e n t="Actual captured rate: "+f p s.t o F i x e d(1).r e p l a c e(/\.0 $/, "")+" FPS"+(f o r m a t?" · "+f o r m a t:"")+(c o n f i g u r e d&&c o n f i g u r e d!=="auto"?" · configured: "+c o n f i g u r e d+" FPS":"")+(c a p t u r e S t a t u s.a c t i v e _ r e s o l u t i o n?" · "+c a p t u r e S t a t u s.a c t i v e _ r e s o l u t i o n:(a c t i v e C o n f i g?.R E S O L U T I O N&&a c t i v e C o n f i g.R E S O L U T I O N!=="auto"?" · "+a c t i v e C o n f i g.R E S O L U T I O N:""))+(c a p t u r e S t a t u s.c a p t u r e _ m o d e==="native_h264_csi"?" · CSI hardware encoder":"")
  }
  e l s e $("capture-rate").t e x t C o n t e n t="Actual captured rate: not currently reported"+(f o r m a t?" · "+f o r m a t:"")
}
a s y n c f u n c t i o n r e f r e s h L i v e S t a t u s() {
  t r y {
    c o n s t d=a w a i t r e q u e s t("/api/live-status");
    r e f r e s h S t a t i s t i c s(d);
    c a p t u r e S t a t u s=d.c a p t u r e _ s t a t u s|| {
    };
    r e n d e r C a p t u r e S t a t u s();
    s y n c O u t p u t M o d e C o n t r o l s();
    c o n s t u p d a t e d=n e w D a t e(d.c a p t u r e _ s t a t u s _ u p d a t e d _ a t*1 0 0 0);
    $("capture-status-freshness").t e x t C o n t e n t="Capture status refreshes every 5 seconds · last updated "+u p d a t e d.t o L o c a l e T i m e S t r i n g()
  }
  c a t c h(e r r o r) {
    $("capture-status-freshness").t e x t C o n t e n t="Live status unavailable: "+e r r o r.m e s s a g e
  }
}
a s y n c f u n c t i o n r e f r e s h S y s t e m I n f o() {
  t r y {
    c o n s t d a t a=a w a i t r e q u e s t("/api/system");
    $("installed-version").t e x t C o n t e n t="Installed version: "+(d a t a.i n s t a l l e d _ v e r s i o n||"unknown")
  }
  c a t c h(e r r o r) {
    $("installed-version").t e x t C o n t e n t="Installed version unavailable: "+e r r o r.m e s s a g e
  }
}
a s y n c f u n c t i o n r e f r e s h R T M P() {
  t r y {
    c o n s t d a t a=a w a i t r e q u e s t("/api/rtmp");
    r t m p S e t t i n g s=d a t a.c o n f i g|| {
      e n a b l e d:f a l s e
    };
    s y n c O u t p u t M o d e C o n t r o l s();
    l e t s o u r c e L a b e l="";
    i f(d a t a.s t a t u s?.s o u r c e==="native_h264"||d a t a.s t a t u s?.s o u r c e==="native_h264_csi")s o u r c e L a b e l=d a t a.s t a t u s.s o u r c e==="native_h264_csi"?"CSI hardware H.264 stream copy":"native H.264 stream copy";
    e l s e i f(d a t a.s t a t u s?.s o u r c e==="mjpeg_copy")s o u r c e L a b e l="MJPEG packet copy";
    l e t s t a t u s T e x t="OBS RTSP feed: "+(d a t a.s t a t u s?.s t a t e||"stopped")+".";
    i f(d a t a.s t a t u s?.a c t i v e) {
      s t a t u s T e x t="OBS RTSP feed is running";
      i f(s o u r c e L a b e l)s t a t u s T e x t+=" ("+s o u r c e L a b e l+")";
      s t a t u s T e x t+="."
    }
    $("rtmp-status").t e x t C o n t e n t=s t a t u s T e x t
  }
  c a t c h(e r r o r) {
    $("rtmp-status").t e x t C o n t e n t="OBS feed status unavailable: "+e r r o r.m e s s a g e
  }
}
a s y n c f u n c t i o n s a v e R T M P() {
  i f(h 2 6 4 M o d e S e l e c t e d O r A c t i v e()) {
    s y n c O u t p u t M o d e C o n t r o l s();
    r e t u r n
  }
  c o n s t d a t a= {
    e n a b l e d:$("rtmp-enabled").c h e c k e d
  };
  $("save-rtmp").d i s a b l e d=t r u e;
  $("rtmp-status").t e x t C o n t e n t="Saving OBS output settings…";
  t r y {
    c o n s t r e s u l t=a w a i t r e q u e s t("/api/rtmp",  {
      m e t h o d:"POST", h e a d e r s: {
        "Content-Type":"application/json"
      }, b o d y:J S O N.s t r i n g i f y(d a t a)
    });
    l e t s o u r c e L a b e l="";
    i f(r e s u l t.s t a t u s?.s o u r c e==="native_h264")s o u r c e L a b e l="native H.264 stream copy";
    e l s e i f(r e s u l t.s t a t u s?.s o u r c e==="mjpeg_copy")s o u r c e L a b e l="MJPEG packet copy";
    l e t s t a t u s T e x t="Settings saved; OBS feed: "+(r e s u l t.s t a t u s?.s t a t e||"stopped")+".";
    i f(r e s u l t.s t a t u s?.a c t i v e) {
      s t a t u s T e x t="OBS feed started";
      i f(s o u r c e L a b e l)s t a t u s T e x t+=" ("+s o u r c e L a b e l+")";
      s t a t u s T e x t+="."
    }
    $("rtmp-status").t e x t C o n t e n t=s t a t u s T e x t
  }
  c a t c h(e r r o r) {
    $("rtmp-status").t e x t C o n t e n t="Unable to save OBS output settings: "+e r r o r.m e s s a g e
  }
  f i n a l l y {
    $("save-rtmp").d i s a b l e d=f a l s e
  }
}
$("save-rtmp").o n c l i c k=s a v e R T M P;
$("refresh-rtmp").o n c l i c k=r e f r e s h R T M P;
f u n c t i o n r e n d e r S t a t C a r d s(r o o t, i t e m s) {
  r o o t.r e p l a c e C h i l d r e n();
  f o r(c o n s t[l a b e l, v a l u e]o f i t e m s) {
    c o n s t c a r d=d o c u m e n t.c r e a t e E l e m e n t("div"), n a m e=d o c u m e n t.c r e a t e E l e m e n t("small"), r e a d i n g=d o c u m e n t.c r e a t e E l e m e n t("strong");
    c a r d.s t y l e.c s s T e x t="background:#1a1d22;border:1px solid #383e47;border-radius:8px;padding:.7rem;min-width:0";
    n a m e.c l a s s N a m e="muted";
    n a m e.t e x t C o n t e n t=l a b e l;
    r e a d i n g.s t y l e.c s s T e x t="display:block;font-size:1.05rem;overflow-wrap:anywhere;margin-top:.2rem";
    r e a d i n g.t e x t C o n t e n t=v a l u e===n u l l||v a l u e===u n d e f i n e d||v a l u e===""?"Not available":S t r i n g(v a l u e);
    c a r d.a p p e n d(n a m e, r e a d i n g);
    r o o t.a p p e n d(c a r d)
  }
}
a s y n c f u n c t i o n r e f r e s h S t a t i s t i c s(d a t a=n u l l) {
  t r y {
    c o n s t d=d a t a||a w a i t r e q u e s t("/api/live-status"), c a p t u r e=d.c a p t u r e _ s t a t u s|| {
    }, s t r e a m=d.s t r e a m _ m e t r i c s|| {
    }, n e t w o r k=d.n e t w o r k _ s t a t u s|| {
    }, c l i e n t s=s t r e a m.c l i e n t s||[], s y s t e m=d.s y s t e m _ m e t r i c s|| {
    }, w i f i=n e t w o r k.w i f i|| {
    };
    c o n s t f p s=c a p t u r e.l a t e s t _ c a p t u r e d _ f p s, d e l i v e r e d=c l i e n t s.l e n g t h?M a t h.m a x(...c l i e n t s.m a p(c l i e n t=>N u m b e r(c l i e n t.a v e r a g e _ f p s||c l i e n t.w i n d o w _ f p s||0))):n u l l, s i g n a l=w i f i.s i g n a l _ d b m, r t m p=d.r t m p _ o u t p u t _ s t a t u s|| {
    };
    c o n s t b a r s=!w i f i.c o n n e c t e d?0:s i g n a l===n u l l||s i g n a l===u n d e f i n e d?n u l l:s i g n a l>=-5 0?4:s i g n a l>=-6 0?3:s i g n a l>=-6 7?2:s i g n a l>=-7 5?1:0;
    c o n s t l a b e l s=["none", "weak", "poor", "good", "excellent"];
    c o n s t r e c e p t i o n=b a r s===n u l l?"unknown":l a b e l s[b a r s];
    c o n s t m e t r i c s=[["Camera FPS", f p s?N u m b e r(f p s).t o F i x e d(1):"Not reported"], ["OBS Feed FPS (RTSP)", r t m p.a c t i v e&&r t m p.f p s!==n u l l&&r t m p.f p s!==u n d e f i n e d&&N u m b e r.i s F i n i t e(N u m b e r(r t m p.f p s))?N u m b e r(r t m p.f p s).t o F i x e d(1):r t m p.e n a b l e d?(r t m p.s t a t e==="stalled"?"No recent output telemetry":r t m p.s t a t e):"Disabled"], ["MJPEG delivered FPS (forwarded JPEG FPS)", d e l i v e r e d===n u l l?"No active viewers":d e l i v e r e d.t o F i x e d(1)], ["Wi-Fi signal", r e c e p t i o n+(s i g n a l===n u l l||s i g n a l===u n d e f i n e d?"":" · "+s i g n a l+" dBm")+" · "+(b a r s===n u l l?"—":"▮".r e p e a t(b a r s)+"▯".r e p e a t(4-b a r s))], ["CPU", s y s t e m.c p u _ p e r c e n t===n u l l||s y s t e m.c p u _ p e r c e n t===u n d e f i n e d?"Not available":N u m b e r(s y s t e m.c p u _ p e r c e n t).t o F i x e d(1)+"%"], ["Memory", s y s t e m.m e m o r y _ u s e d _ m b===u n d e f i n e d?"Not available":s y s t e m.m e m o r y _ u s e d _ m b+" / "+s y s t e m.m e m o r y _ t o t a l _ m b+" MiB"], ["Network Up / Down", n e t w o r k.t x _ m b p s===u n d e f i n e d?"Not available":N u m b e r(n e t w o r k.t x _ m b p s).t o F i x e d(2)+" / "+N u m b e r(n e t w o r k.r x _ m b p s||0).t o F i x e d(2)+" Mbps"]];
    r e n d e r S t a t C a r d s($("system-health-grid"), m e t r i c s);
    $("statistics-updated").t e x t C o n t e n t="Updated "+n e w D a t e(d.c a p t u r e _ s t a t u s _ u p d a t e d _ a t*1 0 0 0).t o L o c a l e T i m e S t r i n g()+" · OBS feed: "+(r t m p.e n a b l e d?(r t m p.s t a t e||"starting"):"disabled")+"; MJPEG delivery is measured separately."
  }
  c a t c h(e r r o r) {
    $("statistics-updated").t e x t C o n t e n t="Statistics unavailable: "+e r r o r.m e s s a g e
  }
}
$("refresh-statistics").o n c l i c k=r e f r e s h S t a t i s t i c s;
a s y n c f u n c t i o n r e f r e s h() {
  $("message").t e x t C o n t e n t="Scanning connected cameras…";
  t r y {
    c o n s t d=a w a i t r e q u e s t("/api/cameras");
    i n v e n t o r y=d.c a m e r a s;
    a c t i v e C o n f i g=d.a c t i v e _ c o n f i g;
    c a p t u r e S t a t u s=d.c a p t u r e _ s t a t u s|| {
    };
    $("camera").r e p l a c e C h i l d r e n();
    i n v e n t o r y.f o r E a c h((c, i)=> {
      c o n s t o=d o c u m e n t.c r e a t e E l e m e n t("option");
      o.v a l u e=i;
      o.t e x t C o n t e n t=c.l a b e l;
      $("camera").a p p e n d(o)
    });
    c o n s t a c t i v e I n d e x=i n v e n t o r y.f i n d I n d e x(c=>a c t i v e C a m e r a M a t c h e s(c, a c t i v e C o n f i g));
    i f(a c t i v e I n d e x>=0) {
      $("camera").v a l u e=S t r i n g(a c t i v e I n d e x);
      $("camera").o p t i o n s[a c t i v e I n d e x].t e x t C o n t e n t+=" · current"
    }
    i f(!i n v e n t o r y.l e n g t h)$("message").t e x t C o n t e n t="No supported cameras detected. Connect a USB or CSI camera and refresh.";
    e l s e {
      c o n s t s e l e c t e d=a c t i v e I n d e x>=0?a c t i v e C o n f i g:n u l l;
      c o n s t s e l e c t e d C a m e r a=a c t i v e I n d e x>=0?i n v e n t o r y[a c t i v e I n d e x]:n u l l;
      c o n s t c u r r e n t R e s o l u t i o n=s e l e c t e d&&s e l e c t e d.R E S O L U T I O N!=="auto"?s e l e c t e d.R E S O L U T I O N:c a p t u r e S t a t u s.a c t i v e _ r e s o l u t i o n;
      c o n s t c u r r e n t F p s=s e l e c t e d&&s e l e c t e d.F P S!=="auto"?N u m b e r(s e l e c t e d.F P S):N u m b e r(c a p t u r e S t a t u s.l a t e s t _ c a p t u r e d _ f p s);
      l e t c u r r e n t F o r m a t=s e l e c t e d&&s e l e c t e d.F O R M A T!=="auto"?s e l e c t e d.F O R M A T:(c a p t u r e S t a t u s.a c t i v e _ c a p t u r e _ f o r m a t||"CSI");
      i f(c u r r e n t F o r m a t==="MJPEG"||c u r r e n t F o r m a t==="JPEG")c u r r e n t F o r m a t="MJPG";
      i f(s e l e c t e d C a m e r a?.k i n d==="csi")c u r r e n t F o r m a t="CSI";
      c o n s t p r e f e r r e d=c u r r e n t R e s o l u t i o n&&c u r r e n t R e s o l u t i o n!=="auto"&&N u m b e r.i s F i n i t e(c u r r e n t F p s)&&c u r r e n t F p s>0? {
        w i d t h:N u m b e r(c u r r e n t R e s o l u t i o n.s p l i t("x")[0]), h e i g h t:N u m b e r(c u r r e n t R e s o l u t i o n.s p l i t("x")[1]), f p s:c u r r e n t F p s, f o r m a t:c u r r e n t F o r m a t
      }
      :n u l l;
      $("message").t e x t C o n t e n t=i n v e n t o r y.l e n g t h+" camera(s) found. Current saved camera settings are selected.";
      f i l l M o d e s(p r e f e r r e d)
    }
    s y n c O u t p u t M o d e C o n t r o l s();
    r e n d e r C a p t u r e S t a t u s();
    a w a i t r e f r e s h C a m e r a C o n t r o l s()
  }
  c a t c h(e) {
    $("message").t e x t C o n t e n t=e.m e s s a g e
  }
}
f u n c t i o n c a m e r a C o n t r o l L a b e l(n a m e) {
  c o n s t l a b e l s= {
    a u t o _ e x p o s u r e:"Auto exposure", e x p o s u r e _ t i m e _ a b s o l u t e:"Exposure time", e x p o s u r e _ d y n a m i c _ f r a m e r a t e:"Dynamic framerate", w h i t e _ b a l a n c e _ a u t o m a t i c:"Automatic white balance", w h i t e _ b a l a n c e _ t e m p e r a t u r e:"White balance temperature", p o w e r _ l i n e _ f r e q u e n c y:"Power-line frequency", b a c k l i g h t _ c o m p e n s a t i o n:"Backlight compensation", f o c u s _ a u t o m a t i c _ c o n t i n u o u s:"Continuous autofocus", f o c u s _ a b s o l u t e:"Focus"
  };
  r e t u r n l a b e l s[n a m e]||n a m e.r e p l a c e A l l("_", " ").r e p l a c e(/\b\w/g, l e t t e r=>l e t t e r.t o U p p e r C a s e())
}
c o n s t p e n d i n g C a m e r a C o n t r o l C h a n g e s=n e w M a p();
f u n c t i o n u p d a t e C a m e r a C o n t r o l D i r t y S t a t e(c o n t r o l, i n p u t, a p p l y B u t t o n) {
  c o n s t v a l u e=c o n t r o l.t y p e==="bool"?(i n p u t.c h e c k e d?1:0):N u m b e r(i n p u t.v a l u e), o r i g i n a l=N u m b e r(c o n t r o l.v a l u e);
  i f(c o n t r o l.v a l u e!==n u l l&&N u m b e r.i s F i n i t e(o r i g i n a l)&&v a l u e===o r i g i n a l)p e n d i n g C a m e r a C o n t r o l C h a n g e s.d e l e t e(c o n t r o l.n a m e);
  e l s e p e n d i n g C a m e r a C o n t r o l C h a n g e s.s e t(c o n t r o l.n a m e, v a l u e);
  a p p l y B u t t o n.d i s a b l e d=p e n d i n g C a m e r a C o n t r o l C h a n g e s.s i z e===0
}
a s y n c f u n c t i o n a p p l y C a m e r a C o n t r o l C h a n g e s() {
  c o n s t b u t t o n=$("apply-camera-controls"), s t a t u s=$("camera-controls-status");
  i f(!p e n d i n g C a m e r a C o n t r o l C h a n g e s.s i z e)r e t u r n;
  b u t t o n.d i s a b l e d=t r u e;
  s t a t u s.t e x t C o n t e n t="Applying camera control changes…";
  t r y {
    f o r(c o n s t[n a m e, v a l u e]o f p e n d i n g C a m e r a C o n t r o l C h a n g e s) {
      a w a i t r e q u e s t("/api/camera-controls",  {
        m e t h o d:"POST", h e a d e r s: {
          "Content-Type":"application/json"
        }, b o d y:J S O N.s t r i n g i f y( {
          n a m e, v a l u e
        })
      });
      p e n d i n g C a m e r a C o n t r o l C h a n g e s.d e l e t e(n a m e)
    }
    s t a t u s.t e x t C o n t e n t="Camera controls updated.";
    a w a i t r e f r e s h C a m e r a C o n t r o l s()
  }
  c a t c h(e r r o r) {
    s t a t u s.t e x t C o n t e n t="Could not apply all camera controls: "+e r r o r.m e s s a g e;
    b u t t o n.d i s a b l e d=p e n d i n g C a m e r a C o n t r o l C h a n g e s.s i z e===0
  }
}
a s y n c f u n c t i o n r e f r e s h C a m e r a C o n t r o l s() {
  c o n s t r o o t=$("camera-controls-list"), s t a t u s=$("camera-controls-status"), a p p l y B u t t o n=$("apply-camera-controls");
  p e n d i n g C a m e r a C o n t r o l C h a n g e s.c l e a r();
  a p p l y B u t t o n.d i s a b l e d=t r u e;
  r o o t.r e p l a c e C h i l d r e n();
  r o o t.s t y l e.c s s T e x t="display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,280px),1fr));gap:.45rem";
  s t a t u s.t e x t C o n t e n t="Reading active camera controls…";
  t r y {
    c o n s t d a t a=a w a i t r e q u e s t("/api/camera-controls");
    i f(!d a t a.s u p p o r t e d) {
      s t a t u s.t e x t C o n t e n t=d a t a.m e s s a g e||"Camera controls are unavailable.";
      r o o t.t e x t C o n t e n t="";
      r e t u r n
    }
    s t a t u s.t e x t C o n t e n t="Controls for "+d a t a.l a b e l+" · "+d a t a.d e v i c e;
    i f(!d a t a.c o n t r o l s.l e n g t h) {
      r o o t.t e x t C o n t e n t="This camera did not report any controls.";
      r e t u r n
    }
    f o r(c o n s t c o n t r o l o f d a t a.c o n t r o l s) {
      c o n s t r o w=d o c u m e n t.c r e a t e E l e m e n t("div"), h e a d i n g=d o c u m e n t.c r e a t e E l e m e n t("div"), l a b e l=d o c u m e n t.c r e a t e E l e m e n t("label"), d e t a i l s=d o c u m e n t.c r e a t e E l e m e n t("small"), e d i t o r=d o c u m e n t.c r e a t e E l e m e n t("div");
      r o w.s t y l e.c s s T e x t="border:1px solid #383e47;border-radius:.5rem;padding:.45rem .6rem;min-width:0;display:grid;grid-template-columns:minmax(0,1fr) auto;gap:.2rem .65rem;align-items:center";
      h e a d i n g.s t y l e.m i n W i d t h="0";
      l a b e l.s t y l e.m a r g i n="0";
      l a b e l.t e x t C o n t e n t=c a m e r a C o n t r o l L a b e l(c o n t r o l.n a m e);
      d e t a i l s.c l a s s N a m e="muted";
      d e t a i l s.s t y l e.c s s T e x t="display:block;font-size:.78rem;line-height:1.25";
      c o n s t i s M e n u=c o n t r o l.t y p e==="menu"||c o n t r o l.t y p e==="intmenu", i s B o o l e a n=c o n t r o l.t y p e==="bool", m e n u O p t i o n=v a l u e=>c o n t r o l.m e n u.f i n d(o p t i o n=>o p t i o n.v a l u e===v a l u e), b o o l e a n L a b e l=v a l u e=>v a l u e===n u l l?"unknown":N u m b e r(v a l u e)===1?"Enabled":"Disabled", d e f a u l t L a b e l=c o n t r o l.d e f a u l t===n u l l?"unavailable":(i s B o o l e a n?b o o l e a n L a b e l(c o n t r o l.d e f a u l t):c o n t r o l.d e f a u l t);
      d e t a i l s.t e x t C o n t e n t="Current: "+(i s M e n u?(m e n u O p t i o n(c o n t r o l.v a l u e)?.l a b e l??"unknown"):(i s B o o l e a n?b o o l e a n L a b e l(c o n t r o l.v a l u e):(c o n t r o l.v a l u e===n u l l?"unknown":c o n t r o l.v a l u e)))+(i s M e n u?" · Default: "+(m e n u O p t i o n(c o n t r o l.d e f a u l t)?.l a b e l??"unavailable")+" · Available: "+c o n t r o l.m e n u.m a p(o p t i o n=>o p t i o n.l a b e l).j o i n(", "):" · Default: "+d e f a u l t L a b e l+(c o n t r o l.m i n!==n u l l&&c o n t r o l.m a x!==n u l l?" · Range: "+c o n t r o l.m i n+"–"+c o n t r o l.m a x:""))+(c o n t r o l.w r i t a b l e?"":" · Currently unavailable");
      e d i t o r.c l a s s N a m e="row";
      e d i t o r.s t y l e.c s s T e x t="align-items:center;gap:.4rem;justify-content:flex-end";
      l e t i n p u t, o u t p u t, i s R a n g e=f a l s e;
      i f(i s B o o l e a n) {
        i n p u t=d o c u m e n t.c r e a t e E l e m e n t("input");
        i n p u t.t y p e="checkbox";
        i n p u t.c h e c k e d=N u m b e r(c o n t r o l.v a l u e)===1;
        i n p u t.i n d e t e r m i n a t e=c o n t r o l.v a l u e===n u l l;
        i n p u t.d i s a b l e d=!c o n t r o l.w r i t a b l e
      }
      e l s e i f(i s M e n u) {
        i n p u t=d o c u m e n t.c r e a t e E l e m e n t("select");
        i f(c o n t r o l.v a l u e===n u l l) {
          c o n s t u n k n o w n=d o c u m e n t.c r e a t e E l e m e n t("option");
          u n k n o w n.v a l u e="";
          u n k n o w n.t e x t C o n t e n t="Unknown";
          u n k n o w n.d i s a b l e d=t r u e;
          i n p u t.a p p e n d(u n k n o w n)
        }
        f o r(c o n s t o p t i o n o f c o n t r o l.m e n u) {
          c o n s t c h o i c e=d o c u m e n t.c r e a t e E l e m e n t("option");
          c h o i c e.v a l u e=o p t i o n.v a l u e;
          c h o i c e.t e x t C o n t e n t=o p t i o n.l a b e l;
          i n p u t.a p p e n d(c h o i c e)
        }
        i n p u t.v a l u e=c o n t r o l.v a l u e===n u l l?"":S t r i n g(c o n t r o l.v a l u e);
        i n p u t.d i s a b l e d=!c o n t r o l.w r i t a b l e;
        i n p u t.s t y l e.m a x W i d t h="10rem"
      }
      e l s e i f(c o n t r o l.t y p e==="int"&&c o n t r o l.v a l u e!==n u l l&&c o n t r o l.m i n!==n u l l&&c o n t r o l.m a x!==n u l l&&c o n t r o l.m a x-c o n t r o l.m i n<=1 0 0 0 0) {
        i s R a n g e=t r u e;
        i n p u t=d o c u m e n t.c r e a t e E l e m e n t("input");
        i n p u t.t y p e="range";
        i n p u t.m i n=c o n t r o l.m i n;
        i n p u t.m a x=c o n t r o l.m a x;
        i n p u t.s t e p=c o n t r o l.s t e p;
        i n p u t.v a l u e=c o n t r o l.v a l u e;
        i n p u t.d i s a b l e d=!c o n t r o l.w r i t a b l e;
        i n p u t.s t y l e.m a x W i d t h="8rem";
        o u t p u t=d o c u m e n t.c r e a t e E l e m e n t("output");
        o u t p u t.t e x t C o n t e n t=i n p u t.v a l u e;
        i n p u t.o n i n p u t=()=> {
          o u t p u t.t e x t C o n t e n t=i n p u t.v a l u e;
          u p d a t e C a m e r a C o n t r o l D i r t y S t a t e(c o n t r o l, i n p u t, a p p l y B u t t o n);
          i f(a d v a n c e d A p p l y H a n d l e)c l e a r T i m e o u t(a d v a n c e d A p p l y H a n d l e);
          a d v a n c e d A p p l y H a n d l e=s e t T i m e o u t(()=> {
            i f(p e n d i n g C a m e r a C o n t r o l C h a n g e s.s i z e)a p p l y C a m e r a C o n t r o l C h a n g e s()
          }, 8 0 0)
        }
      }
      e l s e {
        i n p u t=d o c u m e n t.c r e a t e E l e m e n t("input");
        i n p u t.t y p e="number";
        i f(c o n t r o l.m i n!==n u l l)i n p u t.m i n=c o n t r o l.m i n;
        i f(c o n t r o l.m a x!==n u l l)i n p u t.m a x=c o n t r o l.m a x;
        i n p u t.s t e p=c o n t r o l.s t e p;
        i n p u t.v a l u e=c o n t r o l.v a l u e??"";
        i n p u t.p l a c e h o l d e r=c o n t r o l.v a l u e===n u l l?"Unknown":"";
        i n p u t.d i s a b l e d=!c o n t r o l.w r i t a b l e;
        i n p u t.s t y l e.w i d t h="6rem"
      }
      i f(o u t p u t)e d i t o r.a p p e n d(i n p u t, o u t p u t);
      e l s e e d i t o r.a p p e n d(i n p u t);
      i f(c o n t r o l.w r i t a b l e&&!i s R a n g e)i n p u t.a d d E v e n t L i s t e n e r("change", ()=> {
        u p d a t e C a m e r a C o n t r o l D i r t y S t a t e(c o n t r o l, i n p u t, a p p l y B u t t o n);
        i f(a d v a n c e d A p p l y H a n d l e)c l e a r T i m e o u t(a d v a n c e d A p p l y H a n d l e);
        a d v a n c e d A p p l y H a n d l e=s e t T i m e o u t(()=> {
          i f(p e n d i n g C a m e r a C o n t r o l C h a n g e s.s i z e)a p p l y C a m e r a C o n t r o l C h a n g e s()
        }, 8 0 0)
      });
      h e a d i n g.a p p e n d(l a b e l, d e t a i l s);
      r o w.a p p e n d(h e a d i n g, e d i t o r);
      i f(c o n t r o l.n a m e==="exposure_dynamic_framerate") {
        c o n s t n o t e=d o c u m e n t.c r e a t e E l e m e n t("small");
        n o t e.c l a s s N a m e="muted";
        n o t e.s t y l e.g r i d C o l u m n="1 / -1";
        n o t e.t e x t C o n t e n t="When enabled, the camera may lower its delivered frame rate to accommodate exposure. Disable it if you need a stable frame-rate target.";
        r o w.a p p e n d(n o t e)
      }
      r o o t.a p p e n d(r o w)
    }
  }
  c a t c h(e r r o r) {
    s t a t u s.t e x t C o n t e n t="Camera controls unavailable: "+e r r o r.m e s s a g e
  }
}
$("apply-camera-controls").o n c l i c k=a p p l y C a m e r a C o n t r o l C h a n g e s;
$("refresh-camera-controls").o n c l i c k=r e f r e s h C a m e r a C o n t r o l s;
l e t a d v a n c e d P o l l H a n d l e=n u l l, a d v a n c e d A p p l y H a n d l e=n u l l;
c o n s t a d v a n c e d D i a l o g=$("advanced-camera-dialog");
$("advanced-camera-open").o n c l i c k=()=> {
  a d v a n c e d D i a l o g.s h o w M o d a l();
  r e f r e s h C a m e r a C o n t r o l s();
  i f(a d v a n c e d P o l l H a n d l e)c l e a r I n t e r v a l(a d v a n c e d P o l l H a n d l e);
  a d v a n c e d P o l l H a n d l e=s e t I n t e r v a l(()=> {
    i f(p e n d i n g C a m e r a C o n t r o l C h a n g e s.s i z e===0)r e f r e s h C a m e r a C o n t r o l s()
  }, 6 0 0 0 0)
};
$("advanced-camera-close").o n c l i c k=()=>a d v a n c e d D i a l o g.c l o s e();
a d v a n c e d D i a l o g.a d d E v e n t L i s t e n e r("close", ()=> {
  i f(a d v a n c e d P o l l H a n d l e) {
    c l e a r I n t e r v a l(a d v a n c e d P o l l H a n d l e);
    a d v a n c e d P o l l H a n d l e=n u l l
  }
  i f(a d v a n c e d A p p l y H a n d l e) {
    c l e a r T i m e o u t(a d v a n c e d A p p l y H a n d l e);
    a d v a n c e d A p p l y H a n d l e=n u l l
  }
});
$("refresh").o n c l i c k=r e f r e s h;
$("camera").o n c h a n g e=()=> {
  f i l l M o d e s();
  s y n c O u t p u t M o d e C o n t r o l s()
};
$("apply").o n c l i c k=a s y n c()=> {
  c o n s t c=i n v e n t o r y[+$("camera").v a l u e], m=$("mode").v a l u e;
  i f(!c||!m)r e t u r n;
  c o n s t m o d e=J S O N.p a r s e(m), o v e r r i d e=c o n f i r m P e r f o r m a n c e O v e r r i d e(c, m o d e);
  i f(e x c e e d s P e r f o r m a n c e B u d g e t(c, m o d e)&&!o v e r r i d e)r e t u r n;
  $("apply").d i s a b l e d=t r u e;
  $("message").t e x t C o n t e n t="Applying camera settings…";
  t r y {
    a w a i t r e q u e s t("/api/select",  {
      m e t h o d:"POST", h e a d e r s: {
        "Content-Type":"application/json"
      }, b o d y:J S O N.s t r i n g i f y( {
        k i n d:c.k i n d, c a m e r a _ i d:c.i d, d e v i c e:c.d e v i c e, p h y s i c a l _ p a t h:c.p h y s i c a l _ p a t h, d e v i c e _ p a t h:c.d e v i c e _ p a t h, c a m e r a:c.c a m e r a, m o d e, a l l o w _ p e r f o r m a n c e _ o v e r r i d e:o v e r r i d e
      })
    });
    a w a i t r e f r e s h();
    a w a i t r e f r e s h R T M P();
    $("message").t e x t C o n t e n t=m o d e.f o r m a t==="H264"?"H.264 capture enabled. Use the OBS RTSP Media Source; the HTTP Browser Source is disabled.":"Camera settings saved. The live preview has been reconnected."
  }
  c a t c h(e) {
    $("message").t e x t C o n t e n t=e.m e s s a g e
  }
  f i n a l l y {
    $("apply").d i s a b l e d=f a l s e
  }
};
$("logout").o n c l i c k=a s y n c()=> {
  t r y {
    a w a i t r e q u e s t("/api/logout",  {
      m e t h o d:"POST", h e a d e r s: {
        "Content-Type":"application/json"
      }, b o d y:"{}"
    });
    c s r f T o k e n=n u l l;
    l o c a t i o n.r e l o a d()
  }
  c a t c h(e) {
    a l e r t(e.m e s s a g e)
  }
};
a s y n c f u n c t i o n r e f r e s h T i m e l a p s e() {
  t r y {
    c o n s t d=a w a i t r e q u e s t("/api/timelapse");
    c o n s t c=d.c o n f i g, s=d.s t a t u s;
    $("timelapse-enabled").c h e c k e d=c.e n a b l e d;
    $("timelapse-interval").v a l u e=c.i n t e r v a l _ s e c o n d s;
    $("timelapse-start").v a l u e=c.s c h e d u l e _ s t a r t;
    $("timelapse-end").v a l u e=c.s c h e d u l e _ e n d;
    $("timelapse-retention").v a l u e=c.r e t e n t i o n _ d a y s;
    $("timelapse-storage").v a l u e=c.m a x _ s t o r a g e _ m b;
    $("timelapse-free").v a l u e=c.m i n _ f r e e _ m b;
    $("timelapse-width").v a l u e=c.m a x _ w i d t h;
    $("timelapse-quality").v a l u e=c.j p e g _ q u a l i t y;
    $("timelapse-path").v a l u e=c.s t o r a g e _ p a t h;
    $("timelapse-status").t e x t C o n t e n t="Status: "+s.s t a t e+" · "+s.f r a m e s+" frames · "+M a t h.r o u n d(s.s t o r a g e _ b y t e s/1 0 4 8 5 7 6)+" MiB"+(s.l a s t _ c a p t u r e _ a t?" · Last capture: "+s.l a s t _ c a p t u r e _ a t:"")+(s.l a s t _ e r r o r?" · "+s.l a s t _ e r r o r:"")
  }
  c a t c h(e) {
    $("timelapse-status").t e x t C o n t e n t="Timelapse status unavailable: "+e.m e s s a g e
  }
}
$("refresh-timelapse").o n c l i c k=r e f r e s h T i m e l a p s e;
$("save-timelapse").o n c l i c k=a s y n c()=> {
  c o n s t b=$("save-timelapse");
  b.d i s a b l e d=t r u e;
  t r y {
    a w a i t r e q u e s t("/api/timelapse",  {
      m e t h o d:"POST", h e a d e r s: {
        "Content-Type":"application/json"
      }, b o d y:J S O N.s t r i n g i f y( {
        e n a b l e d:$("timelapse-enabled").c h e c k e d, i n t e r v a l _ s e c o n d s:N u m b e r($("timelapse-interval").v a l u e), s c h e d u l e _ s t a r t:$("timelapse-start").v a l u e, s c h e d u l e _ e n d:$("timelapse-end").v a l u e, r e t e n t i o n _ d a y s:N u m b e r($("timelapse-retention").v a l u e), m a x _ s t o r a g e _ m b:N u m b e r($("timelapse-storage").v a l u e), m i n _ f r e e _ m b:N u m b e r($("timelapse-free").v a l u e), m a x _ w i d t h:N u m b e r($("timelapse-width").v a l u e), j p e g _ q u a l i t y:N u m b e r($("timelapse-quality").v a l u e), s t o r a g e _ p a t h:$("timelapse-path").v a l u e
      })
    });
    a w a i t r e f r e s h T i m e l a p s e()
  }
  c a t c h(e) {
    $("timelapse-status").t e x t C o n t e n t=e.m e s s a g e
  }
  f i n a l l y {
    b.d i s a b l e d=f a l s e
  }
};
r e f r e s h T i m e l a p s e();
a s y n c f u n c t i o n r e f r e s h M o t i o n() {
  t r y {
    c o n s t d=a w a i t r e q u e s t("/api/motion"), c=d.c o n f i g, s=d.s t a t u s;
    $("motion-enabled").c h e c k e d=c.e n a b l e d;
    $("motion-sensitivity").v a l u e=c.s e n s i t i v i t y;
    $("motion-min-change").v a l u e=c.m i n i m u m _ c h a n g e d _ p e r c e n t;
    $("motion-sample").v a l u e=c.s a m p l e _ i n t e r v a l _ s e c o n d s;
    $("motion-confirm").v a l u e=c.c o n f i r m _ s a m p l e s;
    $("motion-cooldown").v a l u e=c.m i n _ e v e n t _ i n t e r v a l _ s e c o n d s;
    $("motion-quiet-enabled").c h e c k e d=c.q u i e t _ h o u r s _ e n a b l e d;
    $("motion-quiet-start").v a l u e=c.q u i e t _ h o u r s _ s t a r t;
    $("motion-quiet-end").v a l u e=c.q u i e t _ h o u r s _ e n d;
    $("motion-retention").v a l u e=c.r e t e n t i o n _ d a y s;
    $("motion-storage").v a l u e=c.m a x _ s t o r a g e _ m b;
    $("motion-free").v a l u e=c.m i n _ f r e e _ m b;
    $("motion-status").t e x t C o n t e n t="Status: "+s.s t a t e+" · "+s.e v e n t _ c o u n t+" events · "+s.s n a p s h o t s+" snapshots · "+M a t h.r o u n d(s.s t o r a g e _ b y t e s/1 0 4 8 5 7 6)+" MiB"+(s.l a s t _ e v e n t _ a t?" · Last event: "+s.l a s t _ e v e n t _ a t:"")+(s.c p u _ p e r c e n t!==u n d e f i n e d?" · Worker CPU: "+s.c p u _ p e r c e n t+"%":"")+(s.p e a k _ r s s _ k i b!==u n d e f i n e d?" · Peak RAM: "+M a t h.r o u n d(s.p e a k _ r s s _ k i b/1 0 2 4)+" MiB":"")+(s.l a s t _ e r r o r?" · "+s.l a s t _ e r r o r:"");
    c o n s t r o o t=$("motion-events");
    r o o t.r e p l a c e C h i l d r e n();
    i f(!s.e v e n t s.l e n g t h) {
      r o o t.t e x t C o n t e n t="No motion events recorded.";
      r e t u r n
    }
    f o r(c o n s t e v e n t o f s.e v e n t s) {
      c o n s t r o w=d o c u m e n t.c r e a t e E l e m e n t("div"), i m g=d o c u m e n t.c r e a t e E l e m e n t("img"), d e t a i l s=d o c u m e n t.c r e a t e E l e m e n t("div"), t i m e=d o c u m e n t.c r e a t e E l e m e n t("div"), c h a n g e=d o c u m e n t.c r e a t e E l e m e n t("small");
      r o w.c l a s s N a m e="motion-event";
      i m g.s r c="/api/motion/events/"+e n c o d e U R I C o m p o n e n t(e v e n t.f i l e);
      i m g.a l t="Motion snapshot "+e v e n t.t i m e s t a m p;
      t i m e.t e x t C o n t e n t=e v e n t.t i m e s t a m p;
      c h a n g e.t e x t C o n t e n t="Changed pixels: "+e v e n t.c h a n g e d _ p e r c e n t+"%";
      d e t a i l s.a p p e n d(t i m e, c h a n g e);
      r o w.a p p e n d(i m g, d e t a i l s);
      r o o t.a p p e n d(r o w)
    }
  }
  c a t c h(e) {
    $("motion-status").t e x t C o n t e n t="Motion status unavailable: "+e.m e s s a g e
  }
}
$("refresh-motion").o n c l i c k=r e f r e s h M o t i o n;
$("save-motion").o n c l i c k=a s y n c()=> {
  c o n s t b=$("save-motion");
  b.d i s a b l e d=t r u e;
  t r y {
    a w a i t r e q u e s t("/api/motion",  {
      m e t h o d:"POST", h e a d e r s: {
        "Content-Type":"application/json"
      }, b o d y:J S O N.s t r i n g i f y( {
        e n a b l e d:$("motion-enabled").c h e c k e d, s e n s i t i v i t y:N u m b e r($("motion-sensitivity").v a l u e), m i n i m u m _ c h a n g e d _ p e r c e n t:N u m b e r($("motion-min-change").v a l u e), s a m p l e _ i n t e r v a l _ s e c o n d s:N u m b e r($("motion-sample").v a l u e), c o n f i r m _ s a m p l e s:N u m b e r($("motion-confirm").v a l u e), m i n _ e v e n t _ i n t e r v a l _ s e c o n d s:N u m b e r($("motion-cooldown").v a l u e), q u i e t _ h o u r s _ e n a b l e d:$("motion-quiet-enabled").c h e c k e d, q u i e t _ h o u r s _ s t a r t:$("motion-quiet-start").v a l u e, q u i e t _ h o u r s _ e n d:$("motion-quiet-end").v a l u e, r e t e n t i o n _ d a y s:N u m b e r($("motion-retention").v a l u e), m a x _ s t o r a g e _ m b:N u m b e r($("motion-storage").v a l u e), m i n _ f r e e _ m b:N u m b e r($("motion-free").v a l u e)
      })
    });
    a w a i t r e f r e s h M o t i o n()
  }
  c a t c h(e) {
    $("motion-status").t e x t C o n t e n t=e.m e s s a g e
  }
  f i n a l l y {
    b.d i s a b l e d=f a l s e
  }
};
r e f r e s h M o t i o n();
s e t I n t e r v a l(r e f r e s h M o t i o n, 1 5 0 0 0);
a s y n c f u n c t i o n r e f r e s h L i g h t S e n s o r() {
  t r y {
    c o n s t d=a w a i t r e q u e s t("/api/light-sensor"), c=d.c o n f i g, s=d.s t a t u s;
    $("light-sensor-enabled").c h e c k e d=c.E N A B L E D;
    $("light-bright-threshold").v a l u e=c.B R I G H T _ T H R E S H O L D _ L U X;
    $("light-dark-threshold").v a l u e=c.D A R K _ T H R E S H O L D _ L U X;
    c o n s t r e a d i n g=s.i l l u m i n a n c e _ l u x===u n d e f i n e d?"No lux reading":s.i l l u m i n a n c e _ l u x+" lx";
    $("light-sensor-status").t e x t C o n t e n t="Status: "+s.s t a t e+" · "+r e a d i n g+(s.e r r o r?" · "+s.e r r o r:"")
  }
  c a t c h(e) {
    $("light-sensor-status").t e x t C o n t e n t="Light sensor status unavailable: "+e.m e s s a g e
  }
}
$("refresh-light-sensor").o n c l i c k=r e f r e s h L i g h t S e n s o r;
$("save-light-sensor").o n c l i c k=a s y n c()=> {
  c o n s t b=$("save-light-sensor");
  b.d i s a b l e d=t r u e;
  t r y {
    a w a i t r e q u e s t("/api/light-sensor",  {
      m e t h o d:"POST", h e a d e r s: {
        "Content-Type":"application/json"
      }, b o d y:J S O N.s t r i n g i f y( {
        E N A B L E D:$("light-sensor-enabled").c h e c k e d, B R I G H T _ T H R E S H O L D _ L U X:N u m b e r($("light-bright-threshold").v a l u e), D A R K _ T H R E S H O L D _ L U X:N u m b e r($("light-dark-threshold").v a l u e)
      })
    });
    a w a i t r e f r e s h L i g h t S e n s o r()
  }
  c a t c h(e) {
    $("light-sensor-status").t e x t C o n t e n t=e.m e s s a g e
  }
  f i n a l l y {
    b.d i s a b l e d=f a l s e
  }
};
r e f r e s h L i g h t S e n s o r();
s e t I n t e r v a l(r e f r e s h L i g h t S e n s o r, 1 0 0 0 0);
a s y n c f u n c t i o n r e f r e s h D i a g n o s t i c s() {
  t r y {
    c o n s t d=a w a i t r e q u e s t("/api/diagnostics");
    c o n s t l a y e r s=d.l a y e r s|| {
    };
    c o n s t f a i l e d=O b j e c t.e n t r i e s(l a y e r s).f i l t e r(([k, v])=>v&&(v.h e a l t h y===f a l s e||v.r e a c h a b l e===f a l s e||v.r e s o l v e d===f a l s e||v.a v a i l a b l e===f a l s e));
    $("diagnostic-summary").t e x t C o n t e n t=f a i l e d.l e n g t h?f a i l e d.m a p(([k])=>k.r e p l a c e A l l("_", " ")+": attention needed").j o i n(" · "):"Local camera, listener, and network checks look healthy.";
    c o n s t u r l s=(d.o b s _ b r o w s e r _ s o u r c e _ u r l s||[]).j o i n("\n");
    $("diagnostic-details").t e x t C o n t e n t="OBS URL(s): "+u r l s+"\n"+(d.p r o b l e m s||[]).j o i n("\n")+"\n"+d.r e m o t e _ c l i e n t _ n o t e
  }
  c a t c h(e) {
    $("diagnostic-summary").t e x t C o n t e n t="Diagnostics unavailable: "+e.m e s s a g e
  }
}
$("refresh-diagnostics").o n c l i c k=r e f r e s h D i a g n o s t i c s;
r e f r e s h D i a g n o s t i c s();
$("download-support-bundle").o n c l i c k=a s y n c()=> {
  c o n s t b=$("download-support-bundle");
  b.d i s a b l e d=t r u e;
  t r y {
    l e t r=a w a i t f e t c h("/api/support-bundle");
    i f(r.s t a t u s===4 0 1) {
      a w a i t l o g i n();
      r=a w a i t f e t c h("/api/support-bundle")
    }
    i f(!r.o k)t h r o w E r r o r("Support bundle request failed ("+r.s t a t u s+")");
    c o n s t b l o b=a w a i t r.b l o b(), u r l=U R L.c r e a t e O b j e c t U R L(b l o b), a=d o c u m e n t.c r e a t e E l e m e n t("a");
    a.h r e f=u r l;
    a.d o w n l o a d="petcam-support.tar.gz";
    d o c u m e n t.b o d y.a p p e n d(a);
    a.c l i c k();
    a.r e m o v e();
    U R L.r e v o k e O b j e c t U R L(u r l)
  }
  c a t c h(e) {
    $("diagnostic-summary").t e x t C o n t e n t="Support bundle failed: "+e.m e s s a g e
  }
  f i n a l l y {
    b.d i s a b l e d=f a l s e
  }
};
a s y n c f u n c t i o n r e f r e s h H e a l t h() {
  t r y {
    c o n s t h=a w a i t r e q u e s t("/api/health");
    $("health-state").t e x t C o n t e n t="Status: "+h.s t a t e.r e p l a c e A l l("_", " ");
    $("health-reason").t e x t C o n t e n t=h.r e a s o n||"No active issue reported.";
    $("health-details").t e x t C o n t e n t="Recoveries: "+(h.r e c o v e r y _ c o u n t||0)+" · Last checked: "+(h.l a s t _ c h e c k e d _ a t||"not yet")+(h.l a s t _ r e c o v e r y _ a t?" · Last recovery: "+h.l a s t _ r e c o v e r y _ a t:"")
  }
  c a t c h(e) {
    $("health-state").t e x t C o n t e n t="Health status unavailable";
    $("health-reason").t e x t C o n t e n t=e.m e s s a g e
  }
}
$("refresh-health").o n c l i c k=r e f r e s h H e a l t h;
r e f r e s h();
r e f r e s h L i v e S t a t u s();
s e t I n t e r v a l(r e f r e s h L i v e S t a t u s, 5 0 0 0);
r e f r e s h S y s t e m I n f o();
r e f r e s h H e a l t h();
s e t I n t e r v a l(r e f r e s h H e a l t h, 3 0 0 0 0);
c o n s t a u t o C h e c k=$("auto-check");
a u t o C h e c k.c h e c k e d=l o c a l S t o r a g e.g e t I t e m("petcam-auto-update-check")==="true";
a u t o C h e c k.o n c h a n g e=()=>l o c a l S t o r a g e.s e t I t e m("petcam-auto-update-check", S t r i n g(a u t o C h e c k.c h e c k e d));
l e t u p d a t e A v a i l a b l e=f a l s e, u p d a t e B u s y=f a l s e;
l e t u p d a t e P o l l T i m e r=n u l l, u p d a t e P o l l I n F l i g h t=f a l s e;
f u n c t i o n s c h e d u l e U p d a t e P o l l(d e l a y=2 0 0 0) {
  i f(u p d a t e P o l l T i m e r)c l e a r T i m e o u t(u p d a t e P o l l T i m e r);
  u p d a t e P o l l T i m e r=s e t T i m e o u t(u p d a t e S t a t u s, d e l a y)
}
a s y n c f u n c t i o n u p d a t e S t a t u s() {
  i f(u p d a t e P o l l I n F l i g h t)r e t u r n;
  u p d a t e P o l l I n F l i g h t=t r u e;
  t r y {
    c o n s t s=a w a i t r e q u e s t("/api/update/status"), w a s B u s y=u p d a t e B u s y;
    u p d a t e B u s y=!!s.a c t i v e;
    c o n s t l a b e l s= {
      s t a r t i n g:"Starting", c h e c k i n g:"Checking release", d o w n l o a d i n g:"Downloading", s t a g i n g:"Staging files", i n s t a l l i n g:"Installing", r e s t a r t i n g:"Restarting services", a u t h e n t i c a t i n g:"Verifying signed release", v e r i f y i n g:"Verifying installation", c o m p l e t e:"Complete", f a i l e d:"Failed", i d l e:"Idle"
    };
    $("update-state").t e x t C o n t e n t=(l a b e l s[s.s t a g e]||s.s t a g e||"Unknown")+(s.a c t i v e?"…":"");
    c o n s t d e t a i l=s.m e s s a g e||"No update has been run yet.";
    c o n s t s t a m p=s.u p d a t e d _ a t?n e w D a t e(s.u p d a t e d _ a t*1 0 0 0).t o L o c a l e T i m e S t r i n g():"";
    $("update-message").t e x t C o n t e n t=d e t a i l+(s t a m p?" · Updated "+s t a m p:"")+(s.w a r n i n g?" · Warning: "+s.w a r n i n g:"");
    $("update-logs").t e x t C o n t e n t=s.l o g s||s.l o g _ w a r n i n g||"No installer output is available.";
    i f(s.a c t i v e) {
      $("install-update").d i s a b l e d=t r u e;
      $("check-updates").d i s a b l e d=t r u e;
      s c h e d u l e U p d a t e P o l l(2 0 0 0)
    }
    e l s e {
      $("check-updates").d i s a b l e d=f a l s e;
      $("install-update").h i d d e n=!u p d a t e A v a i l a b l e;
      $("install-update").d i s a b l e d=!u p d a t e A v a i l a b l e;
      i f(w a s B u s y) {
        u p d a t e B u s y=f a l s e;
        a w a i t r e f r e s h S y s t e m I n f o();
        i f(s.s t a g e==="complete")a w a i t c h e c k U p d a t e s()
      }
    }
  }
  c a t c h(e) {
    $("update-state").t e x t C o n t e n t=u p d a t e B u s y?"Reconnecting…":"Status unavailable";
    $("update-message").t e x t C o n t e n t=u p d a t e B u s y?"The manager connection was interrupted. The installer may still be running; reconnecting automatically.":("Unable to read installer status: "+e.m e s s a g e);
    i f(u p d a t e B u s y)s c h e d u l e U p d a t e P o l l(2 5 0 0);
  }
  f i n a l l y {
    u p d a t e P o l l I n F l i g h t=f a l s e
  }
}
a s y n c f u n c t i o n c h e c k U p d a t e s() {
  c o n s t b=$("check-updates");
  u p d a t e A v a i l a b l e=f a l s e;
  $("install-update").h i d d e n=t r u e;
  b.d i s a b l e d=t r u e;
  $("update-message").t e x t C o n t e n t="Checking signed release metadata…";
  t r y {
    c o n s t d=a w a i t r e q u e s t("/api/update/check");
    u p d a t e A v a i l a b l e=d.u p d a t e _ a v a i l a b l e;
    $("install-update").h i d d e n=!u p d a t e A v a i l a b l e;
    i f(d.s t a t u s==="no-complete-release") {
      $("update-state").t e x t C o n t e n t="No complete release";
      $("update-message").t e x t C o n t e n t="No complete signed PetCam release is currently available. Incomplete releases are skipped automatically; try again later."
    }
    e l s e {
      $("update-state").t e x t C o n t e n t=u p d a t e A v a i l a b l e?"Update available":"Up to date";
      $("update-message").t e x t C o n t e n t=u p d a t e A v a i l a b l e?"A verified application release is available. Review the notes before installing.":"This device is running the latest published PetCam application."
    }
    $("release-notes").t e x t C o n t e n t=(d.r e l e a s e s||[]).f i n d(r=>r.u p d a t e _ a v a i l a b l e)?.r e l e a s e _ n o t e s||((d.r e l e a s e s||[])[0]?.r e l e a s e _ n o t e s)||"No release notes provided by the latest verified release.";
    c o n s t r e l e a s e L i s t=(d.r e l e a s e s||[]).m a p(r=>r.v e r s i o n+" · "+M a t h.c e i l(r.a r c h i v e _ s i z e/1 0 4 8 5 7 6)+" MiB"+(r.u p d a t e _ a v a i l a b l e?" · update":" · installed/current")+(r.r e l e a s e _ n o t e s?"\n"+r.r e l e a s e _ n o t e s:"")).j o i n("\n\n");
    $("update-details").t e x t C o n t e n t="Installed: "+(d.i n s t a l l e d _ v e r s i o n||"unknown")+" · Newest valid: "+(d.a v a i l a b l e _ v e r s i o n||"none")+"\n\nRecent verified releases\n"+(r e l e a s e L i s t||"No complete signed releases found.");
    $("install-update").d i s a b l e d=!u p d a t e A v a i l a b l e||u p d a t e B u s y
  }
  c a t c h(e) {
    $("update-state").t e x t C o n t e n t="Check failed";
    $("update-message").t e x t C o n t e n t=e.m e s s a g e
  }
  f i n a l l y {
    b.d i s a b l e d=f a l s e
  }
}
$("check-updates").o n c l i c k=c h e c k U p d a t e s;
a s y n c f u n c t i o n i n s t a l l U p d a t e() {
  i f(!u p d a t e A v a i l a b l e||u p d a t e B u s y)r e t u r n;
  $("update-confirmation").h i d d e n=t r u e;
  $("install-update").d i s a b l e d=t r u e;
  $("check-updates").d i s a b l e d=t r u e;
  u p d a t e B u s y=t r u e;
  $("update-message").t e x t C o n t e n t="Starting verified update…";
  t r y {
    a w a i t r e q u e s t("/api/update/install",  {
      m e t h o d:"POST", h e a d e r s: {
        "Content-Type":"application/json"
      }, b o d y:"{}"
    });
    $("update-state").t e x t C o n t e n t="Starting…";
    $("update-message").t e x t C o n t e n t="The update has been accepted. Progress is saved on the device; this page will reconnect automatically if the manager restarts.";
    s c h e d u l e U p d a t e P o l l(5 0 0)
  }
  c a t c h(e) {
    $("update-message").t e x t C o n t e n t="The start request did not complete: "+e.m e s s a g e+" Checking whether the updater started…";
    s c h e d u l e U p d a t e P o l l(5 0 0)
  }
}
$("install-update").o n c l i c k=()=> {
  i f(!u p d a t e A v a i l a b l e||u p d a t e B u s y)r e t u r n;
  $("update-confirmation").h i d d e n=f a l s e;
  $("confirm-update-install").f o c u s()
};
$("cancel-update-install").o n c l i c k=()=> {
  $("update-confirmation").h i d d e n=t r u e;
  $("install-update").f o c u s()
};
$("confirm-update-install").o n c l i c k=i n s t a l l U p d a t e;
i f(a u t o C h e c k.c h e c k e d)c h e c k U p d a t e s();
u p d a t e S t a t u s();
(a s y n c()=> {
  t r y {
    c o n s t r e s p o n s e=a w a i t f e t c h("/api/setup/status",  {
      c a c h e:"no-store"
    });
    c o n s t s t a t e=a w a i t r e s p o n s e.j s o n();
    i f(!r e s p o n s e.o k)t h r o w E r r o r(s t a t e.e r r o r||"Unable to check setup status");
    i f(!s t a t e.c o n f i g u r e d) {
      d o c u m e n t.b o d y.c l a s s L i s t.a d d("setup-required");
      $("first-run").h i d d e n=f a l s e
    }
  }
  c a t c h(e r r o r) {
    $("setup-message").t e x t C o n t e n t=e r r o r.m e s s a g e
  }
})();
