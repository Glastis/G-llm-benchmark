/* Random mouse and keyboard input for the T4 game (PLAN §10.28), preloaded before SDL:
 *   FUZZ_SEED=1 FUZZ_MS=20000 LD_PRELOAD=fuzz.so build/city
 * Every 5 ms, the game's next SDL_PollEvent or SDL_WaitEvent* gets a made-up event: a left or right
 * click, a mouse move or a key (the tool keys, space, R, other letters). After FUZZ_MS milliseconds it
 * gets SDL_QUIT, which the game must obey. FUZZ_IDLE=1 sends nothing but that SDL_QUIT. */
#define _GNU_SOURCE
#include <SDL.h>
#include <dlfcn.h>
#include <stdlib.h>

static const SDL_Keycode KEYS[] = {SDLK_1, SDLK_2, SDLK_3, SDLK_4, SDLK_5, SDLK_6, SDLK_SPACE, SDLK_r,
                                   SDLK_a, SDLK_q, SDLK_z, SDLK_7, SDLK_0, SDLK_RETURN, SDLK_TAB};
static unsigned seed;
static Uint32 start, last, duration;
static int idle, quit_sent, ready;

static void setup(void) {
    if (ready)
        return;
    ready = 1;
    seed = (unsigned)atoi(getenv("FUZZ_SEED") ? getenv("FUZZ_SEED") : "1");
    duration = (Uint32)atoi(getenv("FUZZ_MS") ? getenv("FUZZ_MS") : "20000");
    idle = getenv("FUZZ_IDLE") != NULL;
    start = last = SDL_GetTicks();
}

static int pick(int n) { return rand_r(&seed) % n; }

static void mouse(SDL_Event *e) {
    int inside_map = pick(10) < 7;
    int x = inside_map ? pick(24 * 32) : pick(1280), y = inside_map ? pick(16 * 32) : pick(900);
    int kind = pick(3);
    SDL_memset(e, 0, sizeof *e);
    if (kind == 0) {
        e->type = SDL_MOUSEMOTION;
        e->motion.windowID = 1;
        e->motion.x = x;
        e->motion.y = y;
        return;
    }
    e->type = pick(2) ? SDL_MOUSEBUTTONDOWN : SDL_MOUSEBUTTONUP;
    e->button.windowID = 1;
    e->button.button = pick(4) ? SDL_BUTTON_LEFT : SDL_BUTTON_RIGHT;
    e->button.state = e->type == SDL_MOUSEBUTTONDOWN ? SDL_PRESSED : SDL_RELEASED;
    e->button.clicks = 1;
    e->button.x = x;
    e->button.y = y;
}

static void key(SDL_Event *e) {
    SDL_Keycode k = KEYS[pick((int)(sizeof KEYS / sizeof KEYS[0]))];
    SDL_memset(e, 0, sizeof *e);
    e->type = pick(2) ? SDL_KEYDOWN : SDL_KEYUP;
    e->key.windowID = 1;
    e->key.state = e->type == SDL_KEYDOWN ? SDL_PRESSED : SDL_RELEASED;
    e->key.keysym.sym = k;
    e->key.keysym.scancode = SDL_GetScancodeFromKey(k);
}

/* 1 with a made-up event in *e, 0 when the game should read its real queue. */
static int fake(SDL_Event *e) {
    setup();
    Uint32 now = SDL_GetTicks();
    if (now - start >= duration) {
        if (quit_sent++ % 50)   /* keeps sending it, now and then, until the game quits */
            return 0;
        SDL_memset(e, 0, sizeof *e);
        e->type = SDL_QUIT;
        return 1;
    }
    if (idle || now - last < 5)
        return 0;
    last = now;
    if (pick(3))
        mouse(e);
    else
        key(e);
    e->common.timestamp = now;
    return 1;
}

int SDL_PollEvent(SDL_Event *e) {
    static int (*real)(SDL_Event *);
    if (!real)
        real = (int (*)(SDL_Event *))dlsym(RTLD_NEXT, "SDL_PollEvent");
    if (e && fake(e))
        return 1;
    return real(e);
}

int SDL_WaitEventTimeout(SDL_Event *e, int timeout) {
    static int (*real)(SDL_Event *, int);
    if (!real)
        real = (int (*)(SDL_Event *, int))dlsym(RTLD_NEXT, "SDL_WaitEventTimeout");
    if (e && fake(e))
        return 1;
    return real(e, timeout < 0 || timeout > 5 ? 5 : timeout);
}

int SDL_WaitEvent(SDL_Event *e) {
    while (!SDL_WaitEventTimeout(e, 5))
        ;
    return 1;
}
