// Copyright (c) 2026 Louis T Steinhil - Licensed under GNU GPL
// For more information, see LICENSE in the main folder

// Import-free 2025-07-16 telemetry. Only the worker performs configuration/log I/O.
#include "api.h"
typedef unsigned short W;
typedef void* H;
typedef int(__stdcall* Qpc)(cd_i64*);
struct Config {
	cd_u32 moduleIat, procIat, matcher, available;
};
extern "C" __declspec(dllexport) Config ChatDiagnosticsConfig = {};
extern "C" __declspec(dllexport) volatile long ChatDiagnosticsPhase = 0;
extern "C" __declspec(dllexport) ChatDiagLink ChatDiagnosticsLinkData = {7, 1, 63};
extern "C" __declspec(dllexport) const cd_u32 ChatDiagnosticsLayout[] = {sizeof(ChatDiagLink), 12,
	CD_EVENTS, CD_OFFSET(ChatDiagLink, ticks), CD_OFFSET(ChatDiagLink, maximum),
	CD_OFFSET(ChatDiagLink, frequency), sizeof(Config)};
// Bind through the original client kernel imports; optional patch slots may disappear.
struct Kernel {
	H(__stdcall* module)(const char*);
	void*(__stdcall* proc)(H, const char*);
	cd_u32(__stdcall* filename)(H, W*, cd_u32);
	H(__stdcall* open)(const W*, cd_u32, cd_u32, void*, cd_u32, cd_u32, H);
	int(__stdcall* read)(H, void*, cd_u32, cd_u32*, void*);
	int(__stdcall* write)(H, const void*, cd_u32, cd_u32*, void*);
	int(__stdcall* close)(H);
	cd_u32(__stdcall* size)(H, cd_u32*);
	int(__stdcall* move)(const W*, const W*, cd_u32);
	H(__stdcall* thread)(void*, cd_u32, cd_u32(__stdcall*)(void*), void*, cd_u32, cd_u32*);
	void(__stdcall* sleep)(cd_u32);
	cd_u32(__stdcall* tick)();
	cd_u32(__stdcall* pid)();
	cd_u32(__stdcall* tid)();
	void(__stdcall* time)(cd_i64*);
	Qpc qpc, frequency;
};
static Kernel k = {};
static W iniPath[512], logPath[512], oldPath[512];
static H file = (H)-1;
static volatile long stopWorker = 0;
static cd_u32 processId, interval = 1000, resetSequence = 0;
static cd_i64 sessionTime;
struct Frame {
	cd_u32 frame, control;
	cd_i64 start;
	cd_u32 preDone;
};
struct Slot {
	volatile long thread;
	cd_u32 depth;
	Frame frames[8];
};
static Slot slots[8] = {};
struct Snapshot {
	cd_u32 c[CD_EVENTS];
	cd_i64 t[2];
};
static Snapshot previous = {};
static bool invalid(H h) {
	return h == (H)-1 || h == 0;
}
template <class T> static T resolve(H m, const char* name) {
	return reinterpret_cast<T>(k.proc(m, name));
}
static cd_u32 length(const char* s) {
	cd_u32 n = 0;
	while (s[n])
		++n;
	return n;
}
static void append(W* p, cd_u32& n, const char* s) {
	while (*s && n < 510)
		p[n++] = (W)(unsigned char)*s++;
	p[n] = 0;
}
static cd_u32 decimal(char* b, cd_u32 value) {
	char reverse[10];
	cd_u32 n = 0;
	do {
		reverse[n++] = (char)('0' + value % 10);
		value /= 10;
	} while (value);
	for (cd_u32 i = 0; i < n; ++i)
		b[i] = reverse[n - 1 - i];
	return n;
}
static void pathNumber(W* p, cd_u32& n, cd_u32 value) {
	char b[11];
	cd_u32 size = decimal(b, value);
	b[size] = 0;
	append(p, n, b);
}
static bool bind() {
	const Config& c = ChatDiagnosticsConfig;
	if (!c.moduleIat || !c.procIat)
		return false;
	k.module = *reinterpret_cast<decltype(k.module)*>(c.moduleIat);
	k.proc = *reinterpret_cast<decltype(k.proc)*>(c.procIat);
	H module = k.module("kernel32.dll");
	if (!module)
		return false;
#define BIND(member, name)                                                                         \
	k.member = resolve<decltype(k.member)>(module, name);                                          \
	if (!k.member)                                                                                 \
	return false
	BIND(filename, "GetModuleFileNameW");
	BIND(open, "CreateFileW");
	BIND(read, "ReadFile");
	BIND(write, "WriteFile");
	BIND(close, "CloseHandle");
	BIND(size, "GetFileSize");
	BIND(move, "MoveFileExW");
	BIND(thread, "CreateThread");
	BIND(sleep, "Sleep");
	BIND(tick, "GetTickCount");
	BIND(pid, "GetCurrentProcessId");
	BIND(tid, "GetCurrentThreadId");
	BIND(time, "GetSystemTimeAsFileTime");
	BIND(qpc, "QueryPerformanceCounter");
	BIND(frequency, "QueryPerformanceFrequency");
#undef BIND
	cd_u32 n = k.filename(0, iniPath, 512);
	if (!n || n >= 480)
		return false;
	while (n && iniPath[n - 1] != '\\' && iniPath[n - 1] != '/')
		--n;
	for (cd_u32 i = 0; i < n; ++i)
		logPath[i] = oldPath[i] = iniPath[i];
	cd_u32 a = n, b = n;
	append(iniPath, n, "ChatPerformance.ini");
	append(logPath, a, "ChatPerformance.");
	append(oldPath, b, "ChatPerformance.");
	processId = k.pid();
	pathNumber(logPath, a, processId);
	pathNumber(oldPath, b, processId);
	append(logPath, a, ".log");
	append(oldPath, b, ".previous.log");
	k.time(&sessionTime);
	return k.frequency(&ChatDiagnosticsLinkData.frequency) != 0 &&
		ChatDiagnosticsLinkData.frequency > 0;
}
static bool equal(const char* a, cd_u32 size, const char* b) {
	if (size != length(b))
		return false;
	for (cd_u32 i = 0; i < size; ++i)
		if (a[i] != b[i])
			return false;
	return true;
}
struct Settings {
	cd_u32 flags, sample, period, reset;
};
static bool settings(Settings& result) {
	H h = k.open(iniPath, 0x80000000, 7, 0, 3, 0x80, 0);
	if (invalid(h))
		return false;
	char data[2049];
	cd_u32 bytes = 0;
	bool ok = k.read(h, data, 2048, &bytes, 0) != 0;
	k.close(h);
	if (!ok || bytes == 2048)
		return false;
	data[bytes] = 0;
	bool active = false, seen = false;
	cd_u32 at = 0;
	while (at < bytes) {
		cd_u32 start = at;
		while (at < bytes && data[at] != '\n' && data[at] != '\r')
			++at;
		cd_u32 end = at;
		while (at < bytes && (data[at] == '\n' || data[at] == '\r'))
			++at;
		while (start < end && (data[start] == ' ' || data[start] == '\t'))
			++start;
		while (end > start && (data[end - 1] == ' ' || data[end - 1] == '\t'))
			--end;
		if (start == end || data[start] == ';' || data[start] == '#')
			continue;
		if (data[start] == '[') {
			active = equal(data + start, end - start, "[ChatPerformance]");
			seen = seen || active;
			continue;
		}
		if (!active)
			continue;
		cd_u32 split = start;
		while (split < end && data[split] != '=')
			++split;
		if (split == end)
			return false;
		cd_u32 keyEnd = split;
		while (keyEnd > start && (data[keyEnd - 1] == ' ' || data[keyEnd - 1] == '\t'))
			--keyEnd;
		cd_u32 pos = split + 1;
		while (pos < end && (data[pos] == ' ' || data[pos] == '\t'))
			++pos;
		cd_u32 value = 0, digits = 0;
		while (pos < end && data[pos] >= '0' && data[pos] <= '9') {
			if (value > 429496729u || (value == 429496729u && data[pos] > '5'))
				return false;
			value = value * 10 + (data[pos++] - '0');
			++digits;
		}
		while (pos < end && (data[pos] == ' ' || data[pos] == '\t'))
			++pos;
		if (!digits || (pos < end && data[pos] != ';' && data[pos] != '#'))
			return false;
		cd_u32 mask = equal(data + start, keyEnd - start, "stutter_enabled") ? CD_STUTTER
			: equal(data + start, keyEnd - start, "cache_enabled")			 ? CD_CACHE
			: equal(data + start, keyEnd - start, "logging_enabled")		 ? CD_LOGGING
																			 : 0;
		if (mask) {
			if (value > 1)
				return false;
			result.flags = (result.flags & ~mask) | (value ? mask : 0);
		} else if (equal(data + start, keyEnd - start, "sample_every")) {
			if (!value || value > 4096 || (value & (value - 1)))
				return false;
			result.sample = value;
		} else if (equal(data + start, keyEnd - start, "interval_ms")) {
			if (value < 250 || value > 5000)
				return false;
			result.period = value;
		} else if (equal(data + start, keyEnd - start, "reset_sequence"))
			result.reset = value;
		else
			return false;
	}
	return seen;
}
struct Writer {
	char b[2048];
	cd_u32 size;
	void text(const char* s) {
		while (*s && size < sizeof(b) - 6)
			b[size++] = *s++;
	}
	void number(cd_u32 v) {
		if (size < sizeof(b) - 20)
			size += decimal(b + size, v);
	}
	void hex(cd_i64 v) {
		union {
			cd_i64 all;
			cd_u32 p[2];
		} x;
		x.all = v;
		const char* digits = "0123456789abcdef";
		text("\"");
		for (int half = 1; half >= 0; --half)
			for (int shift = 28; shift >= 0; shift -= 4)
				b[size++] = digits[(x.p[half] >> shift) & 15];
		text("\"");
	}
	void key(const char* s) {
		text(",\"");
		text(s);
		text("\":");
	}
};
static bool openLog() {
	if (!invalid(file))
		return true;
	file = k.open(logPath, 4, 7, 0, 4, 0x80, 0);
	return !invalid(file);
}
static void snapshot(Snapshot& s) {
	for (cd_u32 i = 0; i < CD_EVENTS; ++i)
		s.c[i] = (cd_u32)_InterlockedCompareExchange(&ChatDiagnosticsLinkData.counts[i], 0, 0);
	for (cd_u32 i = 0; i < 2; ++i)
		s.t[i] = _InterlockedCompareExchange64(&ChatDiagnosticsLinkData.ticks[i], 0, 0);
}
static const char* const names[CD_EVENTS] = {"append_entered", "temporary_copies_avoided",
	"stock_preprocess_entered", "direct", "wrap", "null_fallback", "append_finished",
	"timing_frames_recovered", "timing_frames_dropped", "glyph_requests", "glyph_hits",
	"glyph_misses", "glyph_native_dispatches", "glyph_disabled", "glyph_fallback", "glyph_busy",
	"fragment_requests", "fragment_hits", "fragment_misses", "fragment_native_calls",
	"fragment_disabled", "fragment_fallback", "fragment_busy", "cache_invalidations",
	"preprocess_samples", "append_samples", "config_errors", "log_errors"};
static void emit(const char* event) {
	Snapshot now;
	snapshot(now);
	if (!openLog()) {
		_InterlockedIncrement(&ChatDiagnosticsLinkData.counts[CD_IO_ERRORS]);
		previous = now;
		return;
	}
	cd_u32 high = 0, low = k.size(file, &high);
	if (high || low > 4194304u) {
		k.close(file);
		file = (H)-1;
		k.move(logPath, oldPath, 1);
		if (!openLog())
			return;
	}
	Writer w;
	w.size = 0;
	w.text("{\"event\":\"");
	w.text(event);
	w.text("\",\"pid\":");
	w.number(processId);
	w.key("session_filetime_hex");
	w.hex(sessionTime);
	w.key("tick_ms");
	w.number(k.tick());
	cd_u32 c = ChatDiagnosticsLinkData.control;
	w.key("phase");
	w.number(c >> 16);
	w.key("stutter_enabled");
	w.number(c & 1);
	w.key("cache_enabled");
	w.number((c >> 1) & 1);
	w.key("logging_enabled");
	w.number((c >> 2) & 1);
	w.key("available_mask");
	w.number(ChatDiagnosticsConfig.available);
	w.key("cache_epoch");
	w.number(ChatDiagnosticsLinkData.cacheEpoch);
	w.key("sample_every");
	w.number(ChatDiagnosticsLinkData.sampleMask + 1);
	w.key("interval_ms");
	w.number(interval);
	w.key("qpc_frequency_hex");
	w.hex(ChatDiagnosticsLinkData.frequency);
	for (cd_u32 i = 0; i < CD_EVENTS; ++i) {
		w.key(names[i]);
		w.number(now.c[i] - previous.c[i]);
	}
	w.key("preprocess_ticks_hex");
	w.hex(now.t[0] - previous.t[0]);
	w.key("append_ticks_hex");
	w.hex(now.t[1] - previous.t[1]);
	w.key("session_preprocess_max_ticks");
	w.number(ChatDiagnosticsLinkData.maximum[0]);
	w.key("session_append_max_ticks");
	w.number(ChatDiagnosticsLinkData.maximum[1]);
	w.text("}\r\n");
	cd_u32 wrote = 0;
	if (!k.write(file, w.b, w.size, &wrote, 0) || wrote != w.size)
		_InterlockedIncrement(&ChatDiagnosticsLinkData.counts[CD_IO_ERRORS]);
	previous = now;
}
static bool apply(const Settings& s) {
	cd_u32 old = ChatDiagnosticsLinkData.control;
	cd_u32 flags = (s.flags & CD_LOGGING) | (s.flags & ChatDiagnosticsConfig.available & 3);
	bool changed = (old & 7) != flags || s.sample != ChatDiagnosticsLinkData.sampleMask + 1 ||
		s.period != interval || s.reset != resetSequence;
	if (!changed)
		return false;
	if ((old & 2) != (flags & 2) || s.reset != resetSequence)
		_InterlockedIncrement(
			reinterpret_cast<volatile long*>(&ChatDiagnosticsLinkData.cacheEpoch));
	interval = s.period;
	resetSequence = s.reset;
	ChatDiagnosticsLinkData.sampleMask = s.sample - 1;
	_InterlockedExchange(reinterpret_cast<volatile long*>(&ChatDiagnosticsLinkData.control),
		((old + 0x10000u) & 0xFFFF0000u) | flags);
	return true;
}
static cd_u32 __stdcall worker(void*) {
	if (ChatDiagnosticsLinkData.control & 4)
		emit("start");
	else
		snapshot(previous);
	cd_u32 last = k.tick();
	while (!_InterlockedCompareExchange(&stopWorker, 0, 0)) {
		k.sleep(250);
		Settings s = {ChatDiagnosticsLinkData.control & 7, ChatDiagnosticsLinkData.sampleMask + 1,
			interval, resetSequence};
		if (settings(s)) {
			cd_u32 before = ChatDiagnosticsLinkData.control;
			if (apply(s)) {
				if ((before & 4) || (ChatDiagnosticsLinkData.control & 4))
					emit("control_change");
				if (!(ChatDiagnosticsLinkData.control & 4) && !invalid(file)) {
					k.close(file);
					file = (H)-1;
				}
				snapshot(previous);
				last = k.tick();
			}
		} else
			_InterlockedIncrement(&ChatDiagnosticsLinkData.counts[CD_CONFIG_ERRORS]);
		cd_u32 now = k.tick();
		if ((ChatDiagnosticsLinkData.control & 4) && now - last >= interval) {
			emit("interval");
			last = now;
		}
	}
	if (ChatDiagnosticsLinkData.control & 4)
		emit("stop");
	if (!invalid(file)) {
		k.close(file);
		file = (H)-1;
	}
	_InterlockedExchange(&stopWorker, 2);
	return 0;
}
static void initialize() {
	if (_InterlockedCompareExchange(&ChatDiagnosticsPhase, 1, 0) != 0)
		return;
	if (!bind()) {
		ChatDiagnosticsLinkData.control = 0;
		_InterlockedExchange(&ChatDiagnosticsPhase, 3);
		return;
	}
	Settings s = {7, 64, 1000, 0};
	settings(s);
	apply(s);
	H h = k.thread(0, 0, worker, 0, 0, 0);
	if (invalid(h)) {
		ChatDiagnosticsLinkData.control = 0;
		_InterlockedExchange(&ChatDiagnosticsPhase, 3);
		return;
	}
	k.close(h);
	_InterlockedExchange(&ChatDiagnosticsPhase, 2);
}
static Slot* slot() {
	if (!k.tid)
		return 0;
	long thread = (long)k.tid();
	for (cd_u32 i = 0; i < 8; ++i)
		if (slots[i].thread == thread)
			return &slots[i];
	for (cd_u32 i = 0; i < 8; ++i)
		if (!_InterlockedCompareExchange(&slots[i].thread, thread, 0))
			return &slots[i];
	chat_count(&ChatDiagnosticsLinkData, CD_DROPPED);
	return 0;
}
static void beginFrame(cd_u32 frame, cd_u32 control, cd_u32 sequence) {
	Slot* s = slot();
	if (!s)
		return;
	while (s->depth && frame >= s->frames[s->depth - 1].frame) {
		--s->depth;
		chat_count(&ChatDiagnosticsLinkData, CD_RECOVERED);
	}
	if ((sequence & ChatDiagnosticsLinkData.sampleMask) != 0 || !k.qpc)
		return;
	if (s->depth >= 8) {
		chat_count(&ChatDiagnosticsLinkData, CD_DROPPED);
		return;
	}
	Frame& f = s->frames[s->depth++];
	f.frame = frame;
	f.control = control;
	f.preDone = 0;
	k.qpc(&f.start);
}
static Frame* findFrame(Slot* s, cd_u32 frame) {
	if (!s)
		return 0;
	for (cd_u32 i = s->depth; i > 0; --i)
		if (s->frames[i - 1].frame == frame)
			return &s->frames[i - 1];
	return 0;
}
static void duration(Frame* f, cd_u32 kind) {
	if (!f || f->control != ChatDiagnosticsLinkData.control || !k.qpc)
		return;
	cd_i64 now;
	k.qpc(&now);
	cd_i64 value = now - f->start;
	if (value < 0)
		return;
	chat_add_ticks(&ChatDiagnosticsLinkData.ticks[kind], value);
	chat_count(&ChatDiagnosticsLinkData, kind ? CD_APPEND_SAMPLES : CD_PRE_SAMPLES);
	union {
		cd_i64 n;
		cd_u32 d[2];
	} v;
	v.n = value;
	if (!v.d[1]) {
		volatile long* maximum =
			reinterpret_cast<volatile long*>(&ChatDiagnosticsLinkData.maximum[kind]);
		long old = *maximum;
		while ((cd_u32)old < v.d[0]) {
			long current = _InterlockedCompareExchange(maximum, (long)v.d[0], old);
			if (current == old)
				break;
			old = current;
		}
	}
}
/** Select the stock, direct or wrapped continuation without replacing native row insertion. */
extern "C" __declspec(dllexport) int __stdcall ChatAppendBegin(const void* text, cd_u32 frame) {
	if (!ChatDiagnosticsPhase)
		initialize();
	if (ChatDiagnosticsPhase != 2)
		return 2;
	ChatDiagLink& d = ChatDiagnosticsLinkData;
	cd_u32 c = d.control;
	if (c & 4) {
		cd_u32 sequence = (cd_u32)_InterlockedIncrement(&d.counts[CD_APPEND]);
		beginFrame(frame, c, sequence);
	}
	if (!text) {
		chat_count(&d, CD_NULL);
		chat_count(&d, CD_STOCK);
		return 2;
	}
	if (!(c & 1) || !ChatDiagnosticsConfig.matcher) {
		chat_count(&d, CD_STOCK);
		return 2;
	}
	int result = ((int(__stdcall*)(const void*))ChatDiagnosticsConfig.matcher)(text);
	chat_count(&d, CD_OPTIMIZED);
	return result ? 1 : 0;
}
extern "C" __declspec(dllexport) void __stdcall ChatRoute(cd_u32 frame, cd_u32 direct) {
	ChatDiagLink& d = ChatDiagnosticsLinkData;
	if (ChatDiagnosticsPhase != 2 || !(d.control & 4))
		return;
	chat_count(&d, direct ? CD_DIRECT : CD_WRAP);
	Frame* f = findFrame(slot(), frame);
	if (f && !f->preDone) {
		f->preDone = 1;
		duration(f, 0);
	}
}
extern "C" __declspec(dllexport) void __stdcall ChatAppendEnd(cd_u32 frame) {
	if (ChatDiagnosticsPhase != 2 || !(ChatDiagnosticsLinkData.control & 4))
		return;
	chat_count(&ChatDiagnosticsLinkData, CD_FINISHED);
	Slot* s = slot();
	Frame* f = findFrame(s, frame);
	if (f) {
		duration(f, 1);
		s->depth = (cd_u32)(f - s->frames);
	}
}
extern "C" __declspec(dllexport) void __stdcall ChatDiagnosticsStop() {
	_InterlockedExchange(&stopWorker, 1);
}
/** Start diagnostics from append or either cache entry, including fragment-only traffic. */
extern "C" __declspec(dllexport) void __stdcall ChatDiagnosticsBootstrap() {
	if (!ChatDiagnosticsPhase)
		initialize();
}
