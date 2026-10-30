// Copyright (c) 2026 Louis T Steinhil - Licensed under GNU GPL
// For more information, see LICENSE in the main folder

// Shared 2025-07-16 x86 diagnostic ABI; hot paths never log message text.
#pragma once

// Minimal x86 interlocked declarations keep the carrier free of CRT/SDK imports.
typedef unsigned int cd_u32;
typedef __int64 cd_i64;
#define CD_OFFSET(type, field) ((cd_u32) & (((type*)0)->field))
extern "C" long __cdecl _InterlockedIncrement(volatile long*);
extern "C" long __cdecl _InterlockedCompareExchange(volatile long*, long, long);
extern "C" long __cdecl _InterlockedExchange(volatile long*, long);
extern "C" cd_i64 __cdecl _InterlockedCompareExchange64(volatile cd_i64*, cd_i64, cd_i64);
#pragma intrinsic(_InterlockedIncrement, _InterlockedCompareExchange, _InterlockedExchange)
#pragma intrinsic(_InterlockedCompareExchange64)
enum ChatEvent {
	CD_APPEND,
	CD_OPTIMIZED,
	CD_STOCK,
	CD_DIRECT,
	CD_WRAP,
	CD_NULL,
	CD_FINISHED,
	CD_RECOVERED,
	CD_DROPPED,
	CD_GLYPH_REQUEST,
	CD_GLYPH_HIT,
	CD_GLYPH_MISS,
	CD_GLYPH_NATIVE,
	CD_GLYPH_DISABLED,
	CD_GLYPH_FALLBACK,
	CD_GLYPH_BUSY,
	CD_FRAGMENT_REQUEST,
	CD_FRAGMENT_HIT,
	CD_FRAGMENT_MISS,
	CD_FRAGMENT_NATIVE,
	CD_FRAGMENT_DISABLED,
	CD_FRAGMENT_FALLBACK,
	CD_FRAGMENT_BUSY,
	CD_INVALIDATE,
	CD_PRE_SAMPLES,
	CD_APPEND_SAMPLES,
	CD_CONFIG_ERRORS,
	CD_IO_ERRORS,
	CD_EVENTS
};
enum { CD_STUTTER = 1, CD_CACHE = 2, CD_LOGGING = 4 };
// Shared data layout is consumed by emitted x86 and independent verifiers.
// Low control bits select fixes/logging; high 16 bits identify a measurement phase.
struct ChatDiagLink {
	volatile cd_u32 control, cacheEpoch, sampleMask;
	volatile long counts[CD_EVENTS];
	__declspec(align(8)) volatile cd_i64 ticks[2];
	volatile cd_u32 maximum[2];
	cd_i64 frequency;
};
static_assert(sizeof(ChatDiagLink) == 160, "Chat diagnostics ABI changed");

static inline cd_u32 chat_control(const ChatDiagLink* p) {
	return p ? p->control : CD_STUTTER | CD_CACHE;
}
static inline void chat_count(ChatDiagLink* p, ChatEvent event) {
	if (p && (p->control & CD_LOGGING))
		_InterlockedIncrement(&p->counts[event]);
}
static inline void chat_add_ticks(volatile cd_i64* target, cd_i64 value) {
	cd_i64 old = _InterlockedCompareExchange64(target, 0, 0);
	for (;;) {
		cd_i64 current = _InterlockedCompareExchange64(target, old + value, old);
		if (current == old)
			return;
		old = current;
	}
}
