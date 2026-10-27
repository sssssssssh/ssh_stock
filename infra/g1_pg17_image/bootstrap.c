#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

/* Single-use image bootstrap. Authorization belongs to the independently installed
 * manager; this program cannot approve a protocol, grant, budget or live run. */
static const char hba[] =
    "local all postgres scram-sha-256\n"
    "local all all scram-sha-256\n"
    "host all all 0.0.0.0/0 reject\n"
    "host all all ::0/0 reject\n";

static void fail(void) {
    static const char error[] = "A42363_BOOTSTRAP_INCOMPLETE\n";
    (void)!write(STDERR_FILENO, error, sizeof(error) - 1);
    _exit(78);
}

static int directory(const char *path, mode_t mode) {
    int fd = open(path, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    struct stat st;
    if (fd < 0 || fstat(fd, &st) || st.st_uid != 999 || st.st_gid != 999 ||
        (st.st_mode & 0777) != mode) fail();
    return fd;
}

static void write_all(int fd, const char *raw, size_t size) {
    while (size) {
        ssize_t n = write(fd, raw, size);
        if (n <= 0) fail();
        raw += n;
        size -= (size_t)n;
    }
}

int main(int argc, char **argv) {
    (void)argv;
    if (argc != 1 || getuid() != 999 || geteuid() != 999 || getgid() != 999 ||
        getegid() != 999 || getgroups(0, NULL) != 0) fail();
    umask(0077);
    if (clearenv() || setenv("PATH", "/usr/lib/postgresql/17/bin:/usr/bin:/bin", 1) ||
        setenv("LANG", "C.UTF-8", 1)) fail();
    int parent = directory("/var/lib/postgresql/data", 0700);
    int socket = directory("/run/postgresql", 0770);
    /* Existing PGDATA is never reinitialized, including after a partial/failed initdb. */
    if (mkdirat(parent, "pgdata", 0700)) fail();
    int data = openat(parent, "pgdata", O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    if (data < 0 || fsync(parent)) fail();
    int secret = open("/run/secrets/space-g1-owner", O_RDONLY | O_NOFOLLOW);
    struct stat st;
    if (secret < 0 || fstat(secret, &st) || !S_ISREG(st.st_mode) || st.st_uid != 999 ||
        st.st_gid != 999 || (st.st_mode & 0777) != 0400 || st.st_nlink != 1 ||
        st.st_size < 64 || st.st_size > 129) fail();
    char secret_path[64];
    if (snprintf(secret_path, sizeof(secret_path), "--pwfile=/proc/self/fd/%d", secret) < 0) fail();
    pid_t pid = fork();
    if (pid < 0) fail();
    if (pid == 0) {
        int null = open("/dev/null", O_RDWR);
        if (null < 0 || dup2(null, 0) < 0 || dup2(null, 1) < 0 || dup2(null, 2) < 0) fail();
        if (null > 2) close(null);
        char *const args[] = {"initdb", "--pgdata=/var/lib/postgresql/data/pgdata",
            "--username=postgres", "--auth-local=scram-sha-256", "--auth-host=reject",
            "--encoding=UTF8", "--locale=C.UTF-8", secret_path, NULL};
        execv("/usr/lib/postgresql/17/bin/initdb", args);
        fail();
    }
    int status;
    while (waitpid(pid, &status, 0) < 0) if (errno != EINTR) fail();
    close(secret);
    if (!WIFEXITED(status) || WEXITSTATUS(status) != 0) fail();
    int out = openat(data, ".space-g1-hba", O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0600);
    if (out < 0) fail();
    write_all(out, hba, sizeof(hba) - 1);
    if (fsync(out) || close(out) || renameat(data, ".space-g1-hba", data, "pg_hba.conf") ||
        fsync(data) || fsync(socket)) fail();
    close(data);
    close(parent);
    close(socket);
    char *const args[] = {"postgres", "-D", "/var/lib/postgresql/data/pgdata",
        "-c", "listen_addresses=", "-c", "unix_socket_directories=/run/postgresql",
        "-c", "unix_socket_permissions=0770", "-c", "password_encryption=scram-sha-256",
        "-c", "max_connections=8", "-c", "shared_buffers=32MB", "-c", "ssl=off", NULL};
    execv("/usr/lib/postgresql/17/bin/postgres", args);
    fail();
}
