// Copyright (c) 2026 Louis T Steinhil - Licensed under GNU GPL
// For more information, see LICENSE in the main folder

// Real Win32 integration of both production payloads; only font/tag boundaries are doubled.
#include <cstddef>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <initializer_list>
#include <windows.h>

#include "../../Scripts/Runtime/ChatDiagnostics/runtime.cpp"
static int __fastcall width(
	const void*, void*, const unsigned char*, unsigned, unsigned, unsigned, unsigned, unsigned);
static unsigned fontGlobals[64] = {}, fontMap[20] = {};
#define CHAT_NATIVE_WIDTH_ADDRESS reinterpret_cast<std::size_t>(&width)
#define CHAT_FONT_GLOBALS_ADDRESS reinterpret_cast<std::size_t>(fontGlobals)
#define CHAT_FONT_MAP_ADDRESS reinterpret_cast<std::size_t>(fontMap)
#include "../../Scripts/Runtime/ChatMeasurementCache/runtime.cpp"

static unsigned nativeWidths = 0, originalCopies = 0;
static volatile unsigned workload = 0;
static void require(bool value, const char* text) {
	if (!value) {
		std::fprintf(stderr, "FAIL %s\n", text);
		std::exit(1);
	}
}
static int __stdcall classify(const void* p) {
	return std::strstr(static_cast<const char*>(p), "<ITEML>") != nullptr;
}
static int __fastcall width(const void*, void*, const unsigned char* text, unsigned length,
	unsigned, unsigned, unsigned, unsigned) {
	++nativeWidths;
	for (unsigned i = 0; i < 1000; ++i)
		workload = workload * 1664525 + 1013904223;
	return static_cast<int>(
		(length ? length : std::strlen(reinterpret_cast<const char*>(text))) * 7);
}
static void writeConfig(
	unsigned stutter, unsigned cache, unsigned logging, unsigned reset, unsigned sample = 1) {
	std::ofstream f("ChatPerformance.pending", std::ios::binary);
	f << "[ChatPerformance]\r\nstutter_enabled=" << stutter << "\r\ncache_enabled=" << cache
	  << "\r\nlogging_enabled=" << logging << "\r\nsample_every=" << sample
	  << "\r\ninterval_ms=250\r\nreset_sequence=" << reset << "\r\n";
	f.close();
	require(MoveFileExA(
				"ChatPerformance.pending", "ChatPerformance.ini", MOVEFILE_REPLACE_EXISTING) != 0,
		"atomic config update");
}
static void waitControl(unsigned flags) {
	for (unsigned i = 0; i < 300 && (ChatDiagnosticsLinkData.control & 7) != flags; ++i)
		Sleep(10);
	require((ChatDiagnosticsLinkData.control & 7) == flags,
		"worker applies independent runtime control");
}
static int message(unsigned char* owner, const char* text) {
	unsigned frame = static_cast<unsigned>(reinterpret_cast<std::size_t>(&owner));
	int route = ChatAppendBegin(text, frame);
	if (route == 2) {
		++originalCopies;
		route = classify(text);
	}
	ChatRoute(frame, route == 1 ? 1 : 0);
	int total = 0;
	for (unsigned i = 0; text[i]; ++i) {
		int result = 0;
		if (!ChatGlyphWidth(owner, reinterpret_cast<const u8*>(text + i), 1, &result))
			result = width(owner, nullptr, reinterpret_cast<const u8*>(text + i), 1, 0, 12, 0, 0);
		total += result;
	}
	total += ChatFragmentWidth(owner, nullptr, reinterpret_cast<const u8*>(text), 0, 0, 12, 0, 0);
	ChatAppendEnd(frame);
	return total;
}
int main() {
	static State state = {};
	ChatCacheApi.state = &state;
	ChatCacheDiagnostics.link = &ChatDiagnosticsLinkData;
	ChatCacheDiagnostics.bootstrap = &ChatDiagnosticsBootstrap;
	ChatCacheDiagnostics.phase = &ChatDiagnosticsPhase;
	unsigned char owner[256] = {};
	*reinterpret_cast<unsigned*>(owner) = 0x102D280;
	auto module = &GetModuleHandleA;
	auto proc = &GetProcAddress;
	ChatDiagnosticsConfig.moduleIat = static_cast<unsigned>(reinterpret_cast<std::size_t>(&module));
	ChatDiagnosticsConfig.procIat = static_cast<unsigned>(reinterpret_cast<std::size_t>(&proc));
	ChatDiagnosticsConfig.matcher = static_cast<unsigned>(reinterpret_cast<std::size_t>(&classify));
	ChatDiagnosticsConfig.available = 3;
	writeConfig(1, 1, 1, 0);
	require(ChatFragmentWidth(owner, nullptr, reinterpret_cast<const u8*>("repeat combat message"),
				0, 0, 12, 0, 0) == 21 * 7,
		"fragment-only traffic initializes logging");
	require(message(owner, "repeat combat message") == 42 * 7,
		"initial real bootstrap preserves measurement");
	require(ChatDiagnosticsPhase == 2, "Win32 bootstrap succeeds");
	waitControl(7);
	unsigned nativeOn = 0, nativeOff = 0;
	unsigned phase = 0;
	for (const auto& flags : {7u, 4u, 5u, 6u}) {
		writeConfig(flags & 1, (flags >> 1) & 1, 1, ++phase);
		waitControl(flags);
		Sleep(300);
		const unsigned before = nativeWidths, copies = originalCopies;
		const long hits = ChatDiagnosticsLinkData.counts[CD_GLYPH_HIT];
		for (unsigned i = 0; i < 100; ++i) {
			require(message(owner, "repeat combat message") == 42 * 7,
				"all four states return identical widths");
			Sleep(3);
		}
		Sleep(300);
		if (flags & 1)
			require(originalCopies == copies, "stutter enabled bypasses original temporary");
		else
			require(originalCopies - copies == 100, "stutter disabled enters stock preprocessing");
		if (flags & 2) {
			require(ChatDiagnosticsLinkData.counts[CD_GLYPH_HIT] > hits,
				"cache enabled records real hits");
			nativeOn += nativeWidths - before;
		} else {
			require(ChatDiagnosticsLinkData.counts[CD_GLYPH_HIT] == hits,
				"cache disabled records zero new hits");
			nativeOff += nativeWidths - before;
		}
	}
	require(nativeOff > nativeOn * 10, "cache reduces actual dispatched width calls");
	require(ChatDiagnosticsLinkData.counts[CD_APPEND_SAMPLES] > 0 &&
			ChatDiagnosticsLinkData.ticks[1] > 0,
		"actual QPC append samples collected");
	require(
		ChatDiagnosticsLinkData.counts[CD_PRE_SAMPLES] > 0 && ChatDiagnosticsLinkData.ticks[0] > 0,
		"actual QPC preprocessing samples collected");
	writeConfig(1, 1, 0, phase);
	waitControl(3);
	Sleep(300);
	long counts[CD_EVENTS];
	for (unsigned i = 0; i < CD_EVENTS; ++i)
		counts[i] = ChatDiagnosticsLinkData.counts[i];
	for (unsigned i = 0; i < 100; ++i)
		require(message(owner, "repeat combat message") == 42 * 7,
			"logging off preserves optimizations");
	for (unsigned i = 0; i < CD_EVENTS; ++i)
		require(counts[i] == ChatDiagnosticsLinkData.counts[i],
			"logging off performs no hot-path counter writes");
	writeConfig(1, 1, 1, ++phase);
	waitControl(7);
	Sleep(300);
	const unsigned frame = 0x30001000;
	ChatAppendBegin("discarded unwind", frame);
	ChatAppendBegin("next call", frame);
	ChatRoute(frame, 0);
	ChatAppendEnd(frame);
	require(
		ChatDiagnosticsLinkData.counts[CD_RECOVERED] > 0, "abandoned sampled frame is recovered");
	const unsigned control = ChatDiagnosticsLinkData.control;
	writeConfig(1, 1, 1, phase, 3);
	Sleep(600);
	require(ChatDiagnosticsLinkData.control == control &&
			ChatDiagnosticsLinkData.counts[CD_CONFIG_ERRORS] > 0,
		"invalid config retains last good policy");
	writeConfig(1, 1, 1, ++phase);
	Sleep(600);
	ChatDiagnosticsStop();
	for (unsigned i = 0; i < 300 && stopWorker != 2; ++i)
		Sleep(10);
	require(stopWorker == 2, "worker closes its log cleanly");
	std::printf(
		"PASS native Win32: four toggle states, identical widths, native calls cache-on=%u "
		"cache-off=%u, sampled timings, logging-off, invalid-config retention, unwind recovery\n",
		nativeOn, nativeOff);
	std::printf("LOG ChatPerformance.%lu.log\n", GetCurrentProcessId());
	return 0;
}
