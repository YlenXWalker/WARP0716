import struct


class ActLayer:
    __slots__ = ('x', 'y', 'sprite_index', 'mirror', 'scale_x', 'scale_y', 'rotation', 'color', 'sprite_type', 'width', 'height')

    def __repr__(self):
        return 'Layer(x=%d,y=%d,spr=%d,mirror=%d,rot=%d,scale=(%.2f,%.2f))' % (
            self.x, self.y, self.sprite_index, self.mirror, self.rotation, self.scale_x, self.scale_y)


class ActFrame:
    __slots__ = ('layers', 'sound_id', 'anchors')


class ActAction:
    __slots__ = ('frames',)


def _load_actions(data, action_count, version, load_anchors):
    pos = 16
    actions = []
    for _ in range(action_count):
        frame_count, = struct.unpack_from('<i', data, pos)
        pos += 4
        frames = []
        for _ in range(frame_count):
            pos += 32  # two range rects, unused for our purposes
            layer_count, = struct.unpack_from('<i', data, pos)
            pos += 4
            layers = []
            for _ in range(layer_count):
                x, y, sprite_index, mirror_raw = struct.unpack_from('<iiii', data, pos)
                pos += 16
                layer = ActLayer()
                layer.x, layer.y, layer.sprite_index, layer.mirror = x, y, sprite_index, (1 if mirror_raw != 0 else 0)
                layer.scale_x = layer.scale_y = 1.0
                layer.rotation = 0
                layer.color = (255, 255, 255, 255)
                layer.sprite_type = 0
                layer.width = layer.height = 0
                if version >= 2.0:
                    r, g, b, a = struct.unpack_from('<BBBB', data, pos)
                    pos += 4
                    layer.color = (r, g, b, a)
                    scale_x, = struct.unpack_from('<f', data, pos)
                    pos += 4
                    layer.scale_x = layer.scale_y = scale_x
                    if version >= 2.4:
                        scale_y, = struct.unpack_from('<f', data, pos)
                        pos += 4
                        layer.scale_y = scale_y
                    rotation, = struct.unpack_from('<i', data, pos)
                    pos += 4
                    layer.rotation = rotation
                    sprite_type, = struct.unpack_from('<i', data, pos)
                    pos += 4
                    layer.sprite_type = sprite_type
                    if version >= 2.5:
                        w, h = struct.unpack_from('<ii', data, pos)
                        pos += 8
                        layer.width, layer.height = w, h
                layers.append(layer)
            frame = ActFrame()
            frame.layers = layers
            frame.sound_id = -1
            frame.anchors = []
            if version >= 2.0:
                sound_id, = struct.unpack_from('<i', data, pos)
                pos += 4
                frame.sound_id = sound_id
            if load_anchors and version >= 2.3:
                anchor_count, = struct.unpack_from('<i', data, pos)
                pos += 4
                for _ in range(anchor_count):
                    unk = data[pos:pos + 4]
                    ax, ay, aattr = struct.unpack_from('<iii', data, pos + 4)
                    pos += 16
                    frame.anchors.append((ax, ay, aattr))
            frames.append(frame)
        action = ActAction()
        action.frames = frames
        actions.append(action)
    return actions, pos


def parse_act(data):
    magic, minor, major = struct.unpack_from('<2sBB', data, 0)
    if magic != b'AC':
        raise ValueError('bad ACT magic: %r' % magic)
    version = major + minor / 10.0
    action_count, = struct.unpack_from('<H', data, 4)

    # Mirror GRF Editor's own documented workaround: versions 2.3/2.4 can have
    # malformed/absent anchor data even though the nominal format calls for it.
    # If a full parse (with anchors) fails, retry once without anchors.
    try:
        actions, pos = _load_actions(data, action_count, version, True)
    except (struct.error, IndexError):
        if 2.3 <= version < 2.5:
            actions, pos = _load_actions(data, action_count, version, False)
        else:
            raise

    return {'major': major, 'minor': minor, 'version': version, 'actions': actions, 'consumed': pos, 'total': len(data)}


if __name__ == '__main__':
    import sys
    from grf_reader import GrfFile

    grf_path = sys.argv[1] if len(sys.argv) > 1 else r'C:\Users\Administrator\Documents\Ragnarok\Banquet of Heroes\spritedata.grf'
    entry = sys.argv[2] if len(sys.argv) > 2 else 'data/sprite/인간족/어세신/어세신_여_1238.act'

    grf = GrfFile(grf_path)
    data = grf.read(entry.lower())
    act = parse_act(data)
    print('version %.1f' % act['version'], 'actions', len(act['actions']),
          'consumed %d / %d bytes' % (act['consumed'], act['total']))
    found = 0
    for ai, action in enumerate(act['actions']):
        for fi, frame in enumerate(action.frames):
            real = [l for l in frame.layers if l.sprite_index >= 0]
            if real and fi == 0:
                print('  action', ai, real)
                found += 1
    print('  action groups with a real layer at frame 0:', found)
