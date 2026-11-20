/* Golden Gate pre-login observer. Reads process identity and delegates observation
 * to Apple's sample and ioreg. Does not signal or modify observed processes. */
#include <libproc.h>
#include <sys/proc_info.h>
#include <sys/event.h>
#include <sys/stat.h>
#include <sys/sysctl.h>
#include <sys/wait.h>
#include <spawn.h>
#include <ctype.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <signal.h>
#include <stdbool.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

extern char **environ;
#define BASE "/private/var/log/hao-diskdiag17"
#define BIN "/Library/Application Support/HAO-DiskDiag17/bin/"
#define MAX_TARGETS 32
struct Seen { pid_t pid; int role; };
static const char *const target_names[] = {
    "mbsystemadministration", "diskimagescontroller", "diskimagesiod",
    "diskarbitrationd", "fskitd", "udf.util", "fstyp", "newfs_apfs"
};
#define N_ROLES ((int)(sizeof target_names / sizeof target_names[0]))
static const char *const service_targets[] = {
    "system/com.apple.diskimagesiod", "system/com.apple.diskimagesiod.ram",
    "system/com.apple.diskimagesiod.spb", "system/com.apple.diskarbitrationd", "system/com.apple.filesystems.fskitd"
};
static const char *const io_classes[] = {
    "AppleDiskImagesController", "DIDeviceCreatorUserClient", "AppleDiskImageDevice", "DIDeviceIOUserClient",
    "IOHDIXController", "IOMedia"
};
#define ARRAY_COUNT(x) (sizeof(x)/sizeof((x)[0]))
/* One sample plus at most one launchctl request per PID and the fixed queries. */
#define N_JOBS (2 * MAX_TARGETS + (int)ARRAY_COUNT(service_targets) + (int)ARRAY_COUNT(io_classes))
static FILE *journal;
static char session[PATH_MAX];
static bool testing;
static pid_t test_children[2], test_exit_child;
static const char *sample_tool = BIN "sample";

static void format(char *dst, size_t capacity, const char *fmt, ...) {
    va_list ap;
    va_start(ap, fmt);
    int length = vsnprintf(dst, capacity, fmt, ap);
    va_end(ap);
    if (length < 0 || (size_t)length >= capacity) {
        fputs("Observer path too long\n", stderr);
        exit(73);
    }
}

static double monotime(void) {
    struct timespec now;
    clock_gettime(CLOCK_MONOTONIC, &now);
    return (double)now.tv_sec + (double)now.tv_nsec / 1e9;
}

static void event(const char *fmt, ...) {
    struct timespec now;
    clock_gettime(CLOCK_REALTIME, &now);
    fprintf(journal, "%lld.%03ld ", (long long)now.tv_sec, now.tv_nsec / 1000000);
    va_list ap;
    va_start(ap, fmt);
    vfprintf(journal, fmt, ap);
    va_end(ap);
    fputc('\n', journal);
    fflush(journal);
}

static void mark(const char *name, const char *message) {
    char path[PATH_MAX];
    format(path, sizeof path, "%s/%s", session, name);
    int fd = open(path, O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW, 0600);
    if (fd < 0 || dprintf(fd, "%s\n", message) < 0) {
        perror(path);
        exit(73);
    }
    (void)fsync(fd);
    close(fd);
}

static void kernel_string(const char *key, char *dst, size_t capacity) {
    size_t size = capacity;
    if (sysctlbyname(key, dst, &size, NULL, 0) != 0 || size < 2) {
        strlcpy(dst, "unknown", capacity);
    }
    dst[capacity - 1] = 0;
}

static void start_session(const char *base) {
    struct stat st;
    if (lstat(base, &st) != 0 || !S_ISDIR(st.st_mode) ||
        (!testing && (st.st_uid != 0 || (st.st_mode & 077) != 0))) {
        fprintf(stderr, "Observer log directory missing or insecure: %s\n", base);
        exit(73);
    }
    char uuid[64] = "self-test";
    if (!testing) {
        kernel_string("kern.bootsessionuuid", uuid, sizeof uuid);
        for (const char *s = uuid; *s; ++s) {
            if (!isxdigit((unsigned char)*s) && *s != '-') {
                strcpy(uuid, "unknown");
                break;
            }
        }
    }
    format(session, sizeof session, "%s/native-%s-XXXXXX", base, uuid);
    if (!mkdtemp(session)) { perror("mkdtemp"); exit(73); }
    mark("STARTED.txt", "Native observer entered main and created this boot session.");
    char path[PATH_MAX], build[64] = "self-test";
    format(path, sizeof path, "%s/events.log", session);
    int fd = open(path, O_CREAT | O_EXCL | O_WRONLY | O_CLOEXEC, 0600);
    if (fd < 0 || !(journal = fdopen(fd, "w"))) { perror(path); exit(73); }
    if (!testing) kernel_string("kern.osversion", build, sizeof build);
    event("started build=%s observer-pid=%d", build, getpid());
}

static int target_index(const char *path) {
    const char *name = strrchr(path, '/');
    name = name ? name + 1 : path;
    for (int i = 0; i < N_ROLES; ++i)
        if (!strcmp(name, target_names[i])) return i;
    return -1;
}

/* Hao can appear as the executable while the guest binary is in argv. Examine
 * only recognized Hao runtimes, never environment strings or unrelated argv. */
static int exact_guest(const char *path) {
    static const char *const paths[] = {
        "/System/Library/CoreServices/Setup Assistant.app/Contents/Resources/mbsystemadministration",
        "/System/Library/PrivateFrameworks/DiskImages2.framework/Versions/A/XPCServices/diskimagescontroller.xpc/Contents/MacOS/diskimagescontroller",
        "/usr/libexec/diskimagesiod", "/usr/libexec/diskarbitrationd", "/usr/libexec/fskitd",
        "/System/Library/Filesystems/udf.fs/Contents/Resources/udf.util", "/sbin/fstyp",
        "/System/Library/Filesystems/apfs.fs/Contents/Resources/newfs_apfs"
    };
    if (!strcmp(path,"/sbin/newfs_apfs")) return 7;
    for (int i = 0; i < N_ROLES; ++i) if (!strcmp(paths[i], path)) return i;
    return -1;
}

static int translated_target(pid_t pid) {
    static char buffer[1 << 20];
    int mib[] = {CTL_KERN, KERN_PROCARGS2, pid}, argc = 0;
    size_t size = sizeof buffer;
    if (sysctl(mib, 3, buffer, &size, NULL, 0) || size < sizeof argc) return -1;
    memcpy(&argc, buffer, sizeof argc);
    char *end = buffer + size, *p = memchr(buffer + sizeof argc, 0, size - sizeof argc);
    if (!p || argc < 1) return -1;
    while (p < end && !*p) ++p;
    /* In the long-lived HAO stage 2, argv[0] is exactly the guest program.
     * Do not confuse a filename in later arguments with a running guest. */
    if (p >= end || !memchr(p, 0, (size_t)(end - p))) return -1;
    return exact_guest(p);
}

static int lookup(struct Seen found[MAX_TARGETS]) {
    int used = 0;
    if (testing) {
        found[0] = (struct Seen){test_children[0],0};
        found[1] = (struct Seen){test_children[1],1};
        if (test_exit_child > 0 && waitpid(test_exit_child,NULL,WNOHANG)==0) {
            found[2]=(struct Seen){test_exit_child,5}; return 3;
        }
        return 2;
    }
    int count = proc_listallpids(NULL, 0);
    if (count < 1 || count > 1000000) {
        event("proc-list unavailable count=%d errno=%d", count, errno);
        return 0;
    }
    size_t capacity = (size_t)count + 128;
    pid_t *pids = calloc(capacity, sizeof *pids);
    if (!pids) return 0;
    int total = proc_listallpids(pids, (int)(capacity * sizeof *pids));
    if (total < 0) event("proc-list failed errno=%d", errno);
    for (int n = 0; n < total && (size_t)n < capacity; ++n) {
        pid_t pid = pids[n];
        if (pid <= 1) continue;
        char path[PROC_PIDPATHINFO_MAXSIZE] = {0};
        if (proc_pidpath(pid, path, sizeof path) <= 0 &&
            proc_name(pid, path, sizeof path) <= 0) continue;
        int index = target_index(path);
        const char *base = strrchr(path, '/');
        base = base ? base + 1 : path;
        if (index < 0 && (!strcmp(base, "hao") || !strcmp(base, "hao-runtime")))
            index = translated_target(pid);
        if (index >= 0) {
            if (used == MAX_TARGETS) { event("process snapshot truncated at %d matches",used); break; }
            found[used++] = (struct Seen){pid,index};
        }
    }
    free(pids);
    return used;
}

static bool device_argument(const char *arg) {
    if (!strncmp(arg,"/dev/",5)) arg+=5;
    if (!strncmp(arg,"rdisk",5)) arg+=5;
    else if (!strncmp(arg,"disk",4)) arg+=4;
    else if (!strncmp(arg,"fd/",3)) arg+=3;
    else return false;
    if (!isdigit((unsigned char)*arg)) return false;
    for (; *arg; ++arg) if (!isdigit((unsigned char)*arg) && *arg!='s') return false;
    return true;
}

static void capture_devices(pid_t pid) {
    static char buffer[262144];
    size_t length=sizeof buffer;
    int mib[]={CTL_KERN,KERN_PROCARGS2,pid}, argc;
    if (!sysctl(mib,3,buffer,&length,NULL,0) && length>sizeof argc) {
        memcpy(&argc,buffer,sizeof argc);
        char *end=buffer+length, *p=memchr(buffer+sizeof argc,0,length-sizeof argc);
        if (p) {
            while (p<end && !*p) p++;
            for (int n=0;n<argc && n<100 && p<end;n++) {
                char *next=memchr(p,0,(size_t)(end-p));
                if (!next) break;
                if (device_argument(p)) event("device-argument pid=%d value=%s",pid,p);
                p=next+1;
            }
        }
    }
    /* Filesystem probes may receive an already-open device rather than its name. */
    struct proc_fdinfo fds[64];
    int n=proc_pidinfo(pid,PROC_PIDLISTFDS,0,fds,sizeof fds);
    for (int i=0; i < n/(int)sizeof fds[0]; i++) {
        if (fds[i].proc_fdtype!=PROX_FDTYPE_VNODE) continue;
        struct vnode_fdinfowithpath vnode={0};
        int got=proc_pidfdinfo(pid,fds[i].proc_fd,PROC_PIDFDVNODEPATHINFO,&vnode,sizeof vnode);
        if (got==(int)sizeof vnode && device_argument(vnode.pvip.vip_path))
            event("device-fd pid=%d fd=%d path=%s",pid,fds[i].proc_fd,vnode.pvip.vip_path);
    }
}

static int was_seen(const struct Seen *seen,int count,struct Seen match) {
    for (int i=0;i<count;i++) if (seen[i].pid==match.pid && seen[i].role==match.role) return 1;
    return 0;
}

static int monitor_probes(void) {
    if(testing) {
        test_exit_child=fork();
        if(!test_exit_child) { usleep(750000); _exit(23); }
    }
    int queue=kqueue();
    if (queue<0) event("exit-monitor-unavailable errno=%d",errno);
    struct Seen previous[MAX_TARGETS], current[MAX_TARGETS];
    int old_count=0;
    double next_mark=0, next_devices=0, end=monotime()+(testing?3:300);
    do {
        int count=lookup(current);
        if (monotime()>=next_mark) {
            event("heartbeat matched=%d polling-ms=200",count);
            next_mark=monotime()+10;
        }
        bool poll_devices=monotime()>=next_devices;
        if (poll_devices) next_devices=monotime()+1;
        for (int i=0;i<count;i++) {
            pid_t pid=current[i].pid;
            if (was_seen(previous,old_count,current[i])) {
                if (!testing && poll_devices && current[i].role>=5) capture_devices(pid);
                continue;
            }
            struct proc_bsdinfo bsd={0};
            int bs=proc_pidinfo(pid,PROC_PIDTBSDINFO,0,&bsd,sizeof bsd);
            char path[PROC_PIDPATHINFO_MAXSIZE]="";
            if (proc_pidpath(pid,path,sizeof path)<=0) strcpy(path,"unavailable");
            event("seen role=%s pid=%d ppid=%d executable=%s",target_names[current[i].role],pid,bs==(int)sizeof bsd?(int)bsd.pbi_ppid:-1,path);
            if (queue>=0) {
                struct kevent change;
                EV_SET(&change,pid,EVFILT_PROC,EV_ADD|EV_ONESHOT,NOTE_EXIT|NOTE_EXITSTATUS,0,(void*)target_names[current[i].role]);
                if (kevent(queue,&change,1,NULL,0,NULL)<0) event("exit-watch-unavailable pid=%d errno=%d",pid,errno);
            }
            if (!testing && current[i].role>=5) capture_devices(pid);
        }
        for (int i=0;i<old_count;i++) if (!was_seen(current,count,previous[i]))
            event("no-longer-visible role=%s pid=%d",target_names[previous[i].role],previous[i].pid);
        memcpy(previous,current,count*sizeof current[0]); old_count=count;
        if (queue>=0) {
            struct kevent changes[MAX_TARGETS]; struct timespec delay={0,200000000};
            int received=kevent(queue,NULL,0,changes,MAX_TARGETS,&delay);
            for (int i=0;i<received;i++) {
                struct kevent *ev=&changes[i]; int status=(int)ev->data;
                if (ev->flags&EV_ERROR) event("exit-status-error pid=%lu error=%lld",(unsigned long)ev->ident,(long long)ev->data);
                else if (ev->fflags&NOTE_EXITSTATUS)
                    event("process-exit role=%s pid=%lu raw=%d exit=%d signal=%d",(char*)ev->udata,
                          (unsigned long)ev->ident,status,WIFEXITED(status)?WEXITSTATUS(status):-1,WIFSIGNALED(status)?WTERMSIG(status):0);
                else event("exit-notified pid=%lu status=unavailable",(unsigned long)ev->ident);
            }
            if(received<0) usleep(200000);
        } else usleep(200000);
    } while(monotime()<end);
    event("process-watch-complete");
    if(queue>=0) close(queue);
    return 0;
}

static pid_t begin_process_watch(void) {
    char path[PATH_MAX];
    format(path,sizeof path,"%s/early-processes.log",session);
    pid_t pid=fork();
    if (pid<0) {event("process-watch-fork-failed errno=%d",errno);return -1;}
    if (!pid) {
        int fd=open(path,O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC|O_NOFOLLOW,0600);
        if(fd<0) _exit(73);
        fclose(journal);
        journal=fdopen(fd,"w");
        if(!journal) _exit(73);
        _exit(monitor_probes());
    }
    return pid;
}

struct Job {
    const char *name;
    pid_t observer_child, target_pid;
    bool stack, timed_out;
    char result[PATH_MAX];
};

static bool launch_job(struct Job *job, const char *tool, char *const argv[], const char *out) {
    posix_spawn_file_actions_t io;
    int err = posix_spawn_file_actions_init(&io);
    if (!err) {
        err = posix_spawn_file_actions_addopen(&io, STDOUT_FILENO, out, O_WRONLY | O_CREAT | O_EXCL, 0600);
        if (!err) err = posix_spawn_file_actions_adddup2(&io, STDOUT_FILENO, STDERR_FILENO);
        if (!err) err = posix_spawn_file_actions_addopen(&io, STDIN_FILENO, "/dev/null", O_RDONLY, 0);
        if (!err) err = posix_spawn(&job->observer_child, tool, &io, NULL, argv, environ);
        posix_spawn_file_actions_destroy(&io);
    }
    if (err) {
        job->observer_child = 0;
        event("spawn-failed %s pid=%d tool=%s error=%s", job->name, job->target_pid, tool, strerror(err));
        return false;
    }
    event("spawned %s pid=%d observer-child=%d tool=%s", job->name, job->target_pid, job->observer_child, tool);
    return true;
}

static int complete_jobs(struct Job jobs[N_JOBS]) {
    double start = monotime();
    int successes = 0;
    for (;;) {
        int pending = 0;
        for (int i = 0; i < N_JOBS; ++i) {
            struct Job *job = &jobs[i];
            if (job->observer_child <= 0) continue;
            int status = 0;
            pid_t result = waitpid(job->observer_child, &status, WNOHANG);
            if (result == 0) {
                ++pending;
                if (!job->timed_out && monotime() - start > 45) {
                    /* Only our unreaped subprocess, never the observed target. */
                    kill(job->observer_child, SIGKILL);
                    job->timed_out = true;
                    event("observer-timeout %s pid=%d", job->name, job->target_pid);
                }
                continue;
            }
            if (result < 0 && errno == EINTR) { ++pending; continue; }
            int rc = result < 0 ? -1 : WIFEXITED(status) ? WEXITSTATUS(status) : 128 + WTERMSIG(status);
            struct stat st;
            bool output = !stat(job->result, &st) && S_ISREG(st.st_mode) && st.st_size > 0;
            if (job->stack && rc == 0 && output && !job->timed_out) {
                ++successes;
                event("sample-ok %s pid=%d bytes=%lld", job->name, job->target_pid, (long long)st.st_size);
            } else {
                event("%s %s pid=%d rc=%d output=%s", job->stack ? "sample-failed" : "query-end",
                      job->name, job->target_pid, rc, output ? "present" : "empty");
            }
            job->observer_child = 0;
        }
        if (!pending) return successes;
        usleep(100000);
    }
}

static int take_round(int number) {
    char dir[PATH_MAX];
    format(dir, sizeof dir, "%s/round-%d", session, number);
    if (mkdir(dir, 0700) != 0) { event("round-create-failed error=%s", strerror(errno)); return 0; }
    event("round %d started", number);
    struct Seen pids[MAX_TARGETS];
    int n = lookup(pids), jobs_used = 0;
    struct Job jobs[N_JOBS] = {0};
    for (int i=0; i<n; i++) {
        pid_t pid = pids[i].pid;
        int role = pids[i].role;
        struct Job *job=&jobs[jobs_used++];
        job->name=target_names[role];
        job->stack=true;
        job->target_pid=pid;
        char id[32], log[PATH_MAX];
        format(id, sizeof id, "%d", pid);
        format(job->result,sizeof job->result,"%s/%s-%d-sample.txt",dir,job->name,pid);
        format(log,sizeof log,"%s/%s-%d-tool.log",dir,job->name,pid);
        char *argv[]={(char *)sample_tool,id,testing ? "1":"3","10","-file",job->result,NULL};
        launch_job(job,sample_tool,argv,log);
        if (!testing && role == 0) {
            struct Job *query=&jobs[jobs_used++];
            char label[128];
            format(label,sizeof label,"pid/%d/com.apple.diskimagescontroller",pid);
            query->name="launchctl-client-domain";
            format(query->result,sizeof query->result,"%s/%s-%d.txt",dir,query->name,pid);
            char *cmd[]={BIN "launchctl","print",label,NULL};
            launch_job(query,cmd[0],cmd,query->result);
        } else if (!testing && (role==1 || role==2)) {
            struct Job *query=&jobs[jobs_used++];
            query->name="launchctl-procinfo";
            format(query->result,sizeof query->result,"%s/%s-%s-%d.txt",dir,query->name,target_names[role],pid);
            char *cmd[]={BIN "launchctl","procinfo",id,NULL};
            launch_job(query,cmd[0],cmd,query->result);
        }
    }
    if (!testing) {
        for (size_t i=0;i<sizeof service_targets/sizeof service_targets[0];i++) {
            struct Job *j=&jobs[jobs_used++];
            j->name=strchr(service_targets[i],'/')+1;
            format(j->result,sizeof j->result,"%s/launchctl-%s.txt",dir,j->name);
            char *cmd[]={BIN "launchctl","print",(char*)service_targets[i],NULL};
            launch_job(j,cmd[0],cmd,j->result);
        }
        for (size_t i=0;i<sizeof io_classes/sizeof io_classes[0];i++) {
            struct Job *j=&jobs[jobs_used++];
            j->name=io_classes[i];
            format(j->result,sizeof j->result,"%s/ioreg-%s.txt",dir,j->name);
            char *cmd[]={BIN "ioreg","-r","-c",(char*)j->name,"-l","-d",
                !strcmp(j->name,"IOMedia") ? "1":"2","-w","0",NULL};
            launch_job(j,cmd[0],cmd,j->result);
        }
    }
    int successes = complete_jobs(jobs);
    event("round %d finished valid-samples=%d", number, successes);
    return successes;
}

static void wait_until(double deadline) {
    while (monotime() < deadline) usleep(200000);
}

static void reap_test_children(void) {
    for (size_t i = 0; i < sizeof test_children / sizeof test_children[0]; ++i)
        if (test_children[i] > 0) {
            kill(test_children[i], SIGTERM);
            while (waitpid(test_children[i], NULL, 0) < 0 && errno == EINTR) {}
        }
}

int main(int argc, char **argv) {
    const char *base = BASE;
    if ((argc == 3 || argc == 4) && !strcmp(argv[1], "--self-test") &&
        geteuid() != 0 && getuid() == geteuid()) {
        testing = true;
        base = argv[2];
        sample_tool = argc == 4 ? argv[3] : "/usr/bin/sample";
    } else if (argc != 1 || geteuid() != 0) {
        fprintf(stderr, "Use without arguments as a system daemon, or --self-test DIR [sample-tool] as an ordinary user.\n");
        return 64;
    }
    umask(077);
    start_session(base);
    if (testing) {
        atexit(reap_test_children);
        for (size_t i = 0; i < sizeof test_children / sizeof test_children[0]; ++i) {
            pid_t pid = fork();
            if (pid < 0) { perror("test fork"); return 71; }
            if (!pid) { for (;;) pause(); }
            test_children[i] = pid;
        }
    }
    pid_t procwatch=begin_process_watch();
    struct Job media={.name="media-watch"};
    if (!testing) {
        format(media.result,sizeof media.result,"%s/early-media.log",session);
        char *args[]={BIN "media-watch",NULL};
        launch_job(&media,args[0],args,media.result);
    }
    struct Seen found[MAX_TARGETS];
    const double deadline = monotime() + (testing ? 1 : 150);
    bool client = false;
    do {
        int n = lookup(found);
        for (int i=0; i<n; i++) if (found[i].role==0) client=true;
        if (client) break;
        if (monotime()<deadline) sleep(testing ? 1 : 2);
    } while (monotime()<deadline);
    event("setup service %s", client ? "observed":"wait-expired");
    const double anchor=monotime();
    wait_until(anchor+(testing ? 0 : 32));
    int total=take_round(1);
    wait_until(anchor+(testing ? 2 : 132));
    total+=take_round(2);
    /* Give both early observers their full five-minute observation window. */
    int status;
    if (procwatch>0) while(waitpid(procwatch,&status,0)<0 && errno==EINTR) {}
    if (media.observer_child>0) {
        pid_t w;
        do { w=waitpid(media.observer_child,&status,0); } while (w<0 && errno==EINTR);
        if(w>0) event("media-watch-ended status=%d",status);
    }
    char note[128];
    format(note, sizeof note, "Two rounds attempted. Valid stack samples: %d", total);
    mark("DONE.txt", note);
    event("done valid-samples=%d", total);
    fclose(journal);
    return total ? 0 : 2;
}
