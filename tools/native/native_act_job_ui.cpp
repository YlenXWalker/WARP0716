// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Louis T Steinhil
/* Native ACT UI surface rasterization, 2025-07-16 x86.
 * Uses the native palette-resolved texture and persistent CSurface pixel buffer.
 * No generated previews, shared-resource mutation, global quad queue or DLL.
 */
using u32 = unsigned int;
using u16 = unsigned short;
using u8 = unsigned char;
extern "C"
{
	int _fltused = 0;
}
struct Layer
{
	int x, y, index, mirror;
	u32 color;
	float sx, sy;
	int angle, type;
};
struct Image
{
	short width, height, repeatX, repeatY;
	void *texture;
};
struct Surface
{
	u32 vtable, width, height, dc, bitmap, previous;
	u32 *pixels;
	u32 dirty, list, count, flags;
};
struct Lock
{
	u32 valid;
	const u8 *pixels;
	int pitch;
	u32 reserved[13];
};
struct Color
{
	float r, g, b, a;
};
static_assert(sizeof(Layer) == 36 && sizeof(Surface) == 44, "2025 ABI");
using LockTexture = void(__thiscall *)(void *, Lock *);
using UnlockTexture = void(__thiscall *)(void *);
using TextureLookup = void *(__thiscall *)(void *, Image *, void *, float *);
using NativeDraw = void(__thiscall *)(void *, int, int, void *, void *, Image *, const Layer *,
									  float, float, u32, void *, float);
static int field(void *p, int off)
{
	return *(int *)((u8 *)p + off);
}
static bool finite(float f)
{
	union
	{
		float f;
		u32 u;
	} v = {f};
	return (v.u & 0x7f800000) != 0x7f800000;
}
static float absolute(float f)
{
	return f < 0 ? -f : f;
}
static int floorInt(float f)
{
	int n = (int)f;
	return f < (float)n ? n - 1 : n;
}
static int ceilInt(float f)
{
	int n = (int)f;
	return f > (float)n ? n + 1 : n;
}
static float clamp(float x, float lo, float hi)
{
	return x < lo ? lo : (x > hi ? hi : x);
}
static void sincosDegrees(float degrees, float *sine, float *cosine)
{
	float radians = degrees * 0.017453292519943295f, s, c;
	__asm { fld radians }
	__asm
	{
		fsincos
	}
	__asm { fstp c }
	__asm {fstp s} *sine = s;
	*cosine = c;
}
static Color pixel(const Lock &lock, int format, int x, int y)
{
	u16 p = *(const u16 *)(lock.pixels + y * lock.pitch + x * 2);
	Color c;
	if (format == 0)
	{ // Native A1R5G5B5, stock expands components with <<3.
		c.a = (p & 0x8000) ? 1.0f : 0.0f;
		c.r = (float)((p >> 7) & 0xf8);
		c.g = (float)((p >> 2) & 0xf8);
		c.b = (float)((p & 31) << 3);
	}
	else
	{ // Native A4R4G4B4, alpha /15 and components <<4.
		c.a = (float)(p >> 12) * (1.0f / 15.0f);
		c.r = (float)((p >> 4) & 0xf0);
		c.g = (float)(p & 0xf0);
		c.b = (float)((p & 15) << 4);
	}
	c.r *= c.a;
	c.g *= c.a;
	c.b *= c.a;
	return c;
}
static Color sample(const Lock &lock, int format, int ox, int oy, int width, int height, float x,
					float y)
{
	// Clamp within this sprite, not neighbouring images in the indexed atlas.
	x = clamp(x, 0, (float)(width - 1));
	y = clamp(y, 0, (float)(height - 1));
	int ix = (int)x, iy = (int)y;
	int nx = ix + 1 < width ? ix + 1 : ix, ny = iy + 1 < height ? iy + 1 : iy;
	float fx = x - (float)ix, fy = y - (float)iy;
	Color a = pixel(lock, format, ox + ix, oy + iy), b = pixel(lock, format, ox + nx, oy + iy);
	Color c = pixel(lock, format, ox + ix, oy + ny), d = pixel(lock, format, ox + nx, oy + ny), v;
	float wa = (1 - fx) * (1 - fy), wb = fx * (1 - fy), wc = (1 - fx) * fy, wd = fx * fy;
	v.r = a.r * wa + b.r * wb + c.r * wc + d.r * wd;
	v.g = a.g * wa + b.g * wb + c.g * wc + d.g * wd;
	v.b = a.b * wa + b.b * wb + c.b * wc + d.b * wd;
	v.a = a.a * wa + b.a * wb + c.a * wc + d.a * wd;
	return v;
}
extern "C" __declspec(dllexport) void __cdecl NativeActRaster(Surface *surface, const Layer *layer,
															  Image *image, void *texture,
															  int sourceX, int sourceY, int anchorX,
															  int anchorY, float scale, float angle)
{
	if (!surface || surface->vtable != 0x00fd5ce4 || !surface->pixels || !layer || !image ||
		!texture || layer->index < 0)
		return;
	if (!surface->width || !surface->height || surface->width > 8192 || surface->height > 8192)
		return;
	int width = image->width, height = image->height, format = field(texture, 4);
	if (width <= 0 || height <= 0 || image->repeatX < 0 || image->repeatY < 0 ||
		(format != 0 && format != 1))
		return;
	if (sourceX < 0 || sourceY < 0 || sourceX + width > field(texture, 0xc) ||
		sourceY + height > field(texture, 0x10))
		return;
	float sx = layer->sx * scale, sy = layer->sy * scale;
	if (!finite(sx) || !finite(sy) || sx <= 0 || sy <= 0 || !finite(angle))
		return;
	float xscale = sx * (float)(image->repeatX + 1), yscale = sy * (float)(image->repeatY + 1);
	float halfW = (float)width * xscale * .5f, halfH = (float)height * yscale * .5f;
	float cx = (float)anchorX + (float)layer->x * sx + halfW,
		  cy = (float)anchorY + (float)layer->y * sy + halfH;
	if (!finite(cx) || !finite(cy) || !finite(halfW) || !finite(halfH) || halfW > 1048576 ||
		halfH > 1048576)
		return;
	float sn = 0, cs = 1;
	if (angle != 0)
		sincosDegrees(angle, &sn, &cs);
	float hw = absolute(cs) * halfW + absolute(sn) * halfH,
		  hh = absolute(sn) * halfW + absolute(cs) * halfH;
	int left = floorInt(clamp(cx - hw, 0, (float)surface->width));
	int right = ceilInt(clamp(cx + hw, 0, (float)surface->width));
	int top = floorInt(clamp(cy - hh, 0, (float)surface->height));
	int bottom = ceilInt(clamp(cy + hh, 0, (float)surface->height));
	if (left >= right || top >= bottom)
		return;
	Lock lock;
	for (volatile u32 *at = (volatile u32 *)&lock; at < (volatile u32 *)(&lock + 1); ++at)
		*at = 0;
	u32 *vt = *(u32 **)texture;
	((LockTexture)vt[4])(texture, &lock);
	if (!(lock.valid & 255))
		return;
	if (!lock.pixels || lock.pitch < field(texture, 0xc) * 2 || lock.pitch > 131072)
	{
		((UnlockTexture)vt[5])(texture);
		return;
	}
	float ta = (float)(layer->color >> 24) * (1.0f / 255.0f);
	float tr = (float)(layer->color & 255) * (1.0f / 255.0f) * ta;
	float tg = (float)((layer->color >> 8) & 255) * (1.0f / 255.0f) * ta;
	float tb = (float)((layer->color >> 16) & 255) * (1.0f / 255.0f) * ta;
	for (int y = top; y < bottom; ++y)
		for (int x = left; x < right; ++x)
		{
			float dx = (float)x + .5f - cx, dy = (float)y + .5f - cy;
			float u = (dx * cs + dy * sn) / xscale + (float)width * .5f;
			float v = (-dx * sn + dy * cs) / yscale + (float)height * .5f;
			if (u < 0 || v < 0 || u >= (float)width || v >= (float)height)
				continue;
			u -= .5f;
			v -= .5f;
			if (layer->mirror & 1)
				u = (float)(width - 1) - u;
			Color c = sample(lock, format, sourceX, sourceY, width, height, u, v);
			float a = c.a * ta;
			if (a <= 0)
				continue;
			u32 &dst = surface->pixels[(u32)y * surface->width + (u32)x];
			float inverse = 1 - a;
			u32 r = (u32)(int)clamp(c.r * tr + (float)((dst >> 16) & 255) * inverse, 0, 255);
			u32 g = (u32)(int)clamp(c.g * tg + (float)((dst >> 8) & 255) * inverse, 0, 255);
			u32 b = (u32)(int)clamp(c.b * tb + (float)(dst & 255) * inverse, 0, 255);
			// Match native DIB storage: the 4444 blit leaves the high byte zero.
			dst = (format == 1 ? 0 : 0xff000000) | (r << 16) | (g << 8) | b;
		}
	((UnlockTexture)vt[5])(texture);
	// Same dirty byte as the native raw blit; cached window composition owns
	// movement, uploads, fade and reopening. No screen coordinates are cached.
	surface->dirty |= 1;
}
extern "C" __declspec(dllexport) void __cdecl NativeActSkillDraw(void *window, const Layer *layer,
																 Image *image, void *texture,
																 const float *atlas, int headX,
																 int headY)
{
	if (!window || !layer || !image)
		return;
	int ox = 0, oy = 0;
	if (layer->type == 0)
	{
		ox = (int)(atlas[3] * 256.0f);
		oy = (int)(atlas[4] * 256.0f);
	}
	NativeActRaster(*(Surface **)((u8 *)window + 0x24), layer, image, texture, ox, oy, headX + 48,
					field(window, 0x18) + headY - 25, 1.0f, (float)layer->angle);
}
extern "C" __declspec(dllexport) void __fastcall
NativeActEquipmentDraw(void *window, void *, int x, int y, void *act, void *spr, Image *image,
					   const Layer *layer, float scale, float angle, u32 tint, void *palette,
					   float extra)
{
	if (!window)
		return;
	if (*(u32 *)window != 0x0103223c)
	{
		((NativeDraw)0x00a1b7c0)(window, x, y, act, spr, image, layer, scale, angle, tint, palette,
								 extra);
		return;
	}
	if (!layer || !image)
		return;
	void *texture = image->texture;
	float atlas[10] = {};
	int ox = 0, oy = 0;
	if (layer->type == 0)
	{
		void *cache = (u8 *)*(void **)0x012515f8 + 0xc0;
		texture = ((TextureLookup)0x00566b70)(cache, image, palette, atlas);
		if (!texture)
			texture = ((TextureLookup)0x005663d0)(cache, image, palette, atlas);
		ox = (int)(atlas[3] * 256.0f);
		oy = (int)(atlas[4] * 256.0f);
	}
	NativeActRaster(*(Surface **)((u8 *)window + 0x24), layer, image, texture, ox, oy, x, y,
					scale * extra, angle);
}
extern "C" __declspec(dllexport) __declspec(naked) void NativeActSkillBridge()
{
	__asm {
		pushfd
		pushad
		push dword ptr [ebp-0e8h]
		push dword ptr [ebp-0e0h]
		lea eax,[ebp-130h]
		push eax
		push dword ptr [ebp-0d8h]
		push dword ptr [ebp-0d4h]
		push dword ptr [ebp-0dch]
		push dword ptr [ebp-0ech]
		call NativeActSkillDraw
		add esp,28
		popad
		popfd
		push 00974f61h
		ret
	}
}
