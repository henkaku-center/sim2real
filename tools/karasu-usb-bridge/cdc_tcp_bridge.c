#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <linux/usb/ch9.h>
#include <linux/usbdevice_fs.h>
#include <netinet/in.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/select.h>
#include <sys/socket.h>
#include <time.h>
#include <unistd.h>

static int usbfd = -1;
static unsigned ep_out = 0x03, ep_in = 0x84;
static int iface0 = 0, iface1 = 1;
static volatile sig_atomic_t stop_flag = 0;

static void on_sig(int sig){ (void)sig; stop_flag = 1; }

static int ctrl(int fd, unsigned char rt, unsigned char req, unsigned short val, unsigned short idx, void* data, unsigned short len){
  struct usbdevfs_ctrltransfer c; memset(&c,0,sizeof(c));
  c.bRequestType=rt; c.bRequest=req; c.wValue=val; c.wIndex=idx; c.wLength=len; c.data=data; c.timeout=1000;
  return ioctl(fd, USBDEVFS_CONTROL, &c);
}
static int bulk(int fd, unsigned ep, void* data, int len, unsigned timeout){
  struct usbdevfs_bulktransfer b; memset(&b,0,sizeof(b)); b.ep=ep; b.len=len; b.data=data; b.timeout=timeout;
  return ioctl(fd, USBDEVFS_BULK, &b);
}
static void set_line(unsigned baud){
  unsigned char line[7];
  line[0]=baud & 0xff; line[1]=(baud>>8)&0xff; line[2]=(baud>>16)&0xff; line[3]=(baud>>24)&0xff;
  line[4]=0; line[5]=0; line[6]=8; // 8N1
  ctrl(usbfd,0x21,0x20,0,iface0,line,7);
}
static void set_dtr_rts(int dtr, int rts){
  unsigned val = (dtr?1:0) | (rts?2:0);
  ctrl(usbfd,0x21,0x22,val,iface0,NULL,0);
}
static void claim_interfaces(void){
  struct usbdevfs_disconnect_claim dc; memset(&dc,0,sizeof(dc));
  dc.flags=USBDEVFS_DISCONNECT_CLAIM_EXCEPT_DRIVER;
  dc.interface=iface0; ioctl(usbfd, USBDEVFS_DISCONNECT_CLAIM, &dc);
  dc.interface=iface1; ioctl(usbfd, USBDEVFS_DISCONNECT_CLAIM, &dc);
  unsigned int i0=iface0, i1=iface1;
  if(ioctl(usbfd, USBDEVFS_CLAIMINTERFACE, &i0)<0) perror("claim iface0");
  if(ioctl(usbfd, USBDEVFS_CLAIMINTERFACE, &i1)<0) perror("claim iface1");
}
static int listen_port(int port){
  int s=socket(AF_INET,SOCK_STREAM,0); if(s<0){perror("socket"); exit(1);} int one=1;
  setsockopt(s,SOL_SOCKET,SO_REUSEADDR,&one,sizeof(one));
  struct sockaddr_in a; memset(&a,0,sizeof(a)); a.sin_family=AF_INET; a.sin_addr.s_addr=htonl(INADDR_ANY); a.sin_port=htons(port);
  if(bind(s,(struct sockaddr*)&a,sizeof(a))<0){perror("bind"); exit(1);} if(listen(s,1)<0){perror("listen"); exit(1);} return s;
}
int main(int argc, char **argv){
  if(argc < 2){ fprintf(stderr,"usage: %s usb_fd [tcp_port]\n", argv[0]); return 2; }
  usbfd=atoi(argv[1]); int port = argc>=3 ? atoi(argv[2]) : 7777;
  signal(SIGTERM,on_sig); signal(SIGINT,on_sig); signal(SIGPIPE,SIG_IGN);
  claim_interfaces(); set_line(115200); set_dtr_rts(1,1);
  int ls=listen_port(port); fprintf(stderr,"cdc_tcp_bridge listening on %d, usb fd %d\n", port, usbfd); fflush(stderr);
  unsigned char buf[4096];
  while(!stop_flag){
    struct sockaddr_in ca; socklen_t cl=sizeof(ca); int cs=accept(ls,(struct sockaddr*)&ca,&cl);
    if(cs<0){ if(errno==EINTR) continue; perror("accept"); break; }
    fprintf(stderr,"client connected\n"); fflush(stderr);
    fcntl(cs,F_SETFL,fcntl(cs,F_GETFL,0)|O_NONBLOCK);
    // leave DTR/RTS asserted for app/bootloader CDC. Socket URL cannot control them.
    while(!stop_flag){
      fd_set rf; FD_ZERO(&rf); FD_SET(cs,&rf); struct timeval tv={0,1000};
      int sr=select(cs+1,&rf,NULL,NULL,&tv);
      if(sr>0 && FD_ISSET(cs,&rf)){
        int n=read(cs,buf,sizeof(buf));
        if(n==0){ fprintf(stderr,"client closed\n"); break; }
        if(n<0 && errno!=EAGAIN && errno!=EWOULDBLOCK){ perror("tcp read"); break; }
        if(n>0){ int off=0; while(off<n){ int w=bulk(usbfd,ep_out,buf+off,n-off,1000); if(w<0){perror("usb write"); break;} off+=w; } }
      }
      int r=bulk(usbfd,ep_in,buf,sizeof(buf),1);
      if(r>0){ int off=0; while(off<r){ int w=write(cs,buf+off,r-off); if(w<0){ if(errno==EAGAIN||errno==EWOULDBLOCK) continue; perror("tcp write"); goto done_client;} off+=w; } }
      else if(r<0 && errno!=ETIMEDOUT && errno!=EAGAIN && errno!=EPIPE) { /* many kernels use ETIMEDOUT for no data */ }
    }
 done_client:
    close(cs);
  }
  close(ls); return 0;
}
