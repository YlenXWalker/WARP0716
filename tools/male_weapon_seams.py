"""Join a handle-component terminal texel to an exposed body texel.

The native generic hilt supplies the hand vicinity. Only exterior body texels
are candidates; there is no clearance of a broad mask against the whole weapon.
The pair of supporting corners is the precise seam contract. It does not claim
whole-body occlusion or anatomically identify an unseen fist.
"""
import numpy as np

# Authored from the actual six held-body SPR images, not a generic crossguard
# projected onto the collar. Each row is (lower/across-body fist, raised fist).
# Coordinates identify an opaque texel whose TOP edge is the hilt contact.
# Body names and SPR content are independently pinned by the profile generator.
HELD_FISTS = {
    0: [((12,20),(12,8)),((13,21),(13,9)),((14,22),(14,10)),
        ((13,21),(12,10)),((12,20),(11,9)),((11,20),(10,8))],
    1: [((12,20),(12,8)),((13,21),(13,9)),((14,22),(14,10)),
        ((13,21),(12,10)),((12,20),(11,9)),((11,20),(10,8))],
    2: [((13,18),(13,8)),((15,19),(14,9)),((16,20),(15,10)),
        ((14,19),(13,11)),((13,18),(12,10)),((12,18),(11,9))],
    3: [((16,20),(14,9)),((16,21),(14,10)),((17,22),(15,11)),
        ((16,22),(13,12)),((15,21),(12,11)),((14,20),(11,10))],
    4: [((12,21),(13,10)),((12,22),(13,11)),((13,23),(14,12)),
        ((12,22),(12,12)),((11,21),(11,11)),((10,20),(10,10))],
}
# Complete front-held originals: explicitly reviewed terminal handle texels.
# Views 44/45/46 extend beyond the old Chebyshev-radius-8 search window.
HELD_TERMINALS = {
    1:(0,8,22),2:(0,15,30),6:(0,22,28),34:(0,13,26),35:(0,21,21),
    36:(0,11,24),37:(0,3,38),38:(0,9,22),39:(0,5,50),40:(0,5,32),
    41:(0,5,40),42:(0,3,47),43:(0,5,45),44:(0,4,52),
    45:(0,9,56),46:(0,9,56),47:(0,3,48),
    31:(2,10,1),32:(2,17,7),33:(2,15,2),
}

def authored_held_contact(body, bm, weapon, wm, body_id, body_image, role, view, weapon_image):
    assert 54 <= body_image <= 59
    bp=HELD_FISTS[body_id][body_image-54][role]
    index,x,y=HELD_TERMINALS[view];wp=(x,y)
    assert index==weapon_image,(view,index,weapon_image)
    assert bp in {tuple(map(int,p)) for p in body},(body_id,body_image,role,bp)
    assert wp in {tuple(map(int,p)) for p in weapon},(view,wp)
    # Top of the identified fist; the handle texel's supporting corner toward
    # that face. Interior neighboring body pixels can be collar/other arm and
    # must not move an anatomical hand landmark out to the body silhouette.
    bc=np.array(bp,dtype=float)+(.5,0.)
    inward=bm[:,1]/np.linalg.norm(bm[:,1])
    wc=np.array(wp,dtype=float)+.5+.5*np.sign(wm.T@inward)
    return bc,wc,dict(method='authored_fist_top_edge_to_explicit_handle_terminal',
        body_pixel=list(bp),weapon_pixel=list(wp),hand_mask=[list(bp)],
        body_image=body_image,weapon_image=weapon_image,
        contact_normal=(-inward).tolist(),hand_annotation='HELD_FISTS',
        terminal_annotation='HELD_TERMINALS')

def endpoint_contact(body,seed,bm,weapon,grip,tip,wm):
    opaque={tuple(map(int,p)) for p in body}
    direction=wm@(np.array(tip)-grip);direction/=np.linalg.norm(direction)
    inward=np.linalg.solve(bm,direction)
    # Exposed faces looking toward the blade, rather than the opposite edge of
    # the torso. Rank by distance to the artist-authored generic grip location.
    boundary=[]
    for pixel in opaque:
        exposed=[(dx,dy) for dx,dy in ((1,0),(-1,0),(0,1),(0,-1))
                 if (pixel[0]+dx,pixel[1]+dy) not in opaque and np.dot((dx,dy),inward)>0]
        if exposed:boundary.append(pixel)
    bp=min(boundary,key=lambda p:(np.sum((np.array(p)-seed)**2),p))
    assert np.linalg.norm(np.array(bp)-seed)<12,(seed,bp)
    # Keep the connected opaque hilt component nearest the explicit grip seed.
    # Detached pommels/other perspective pieces cannot drive the seam solver.
    nearby={tuple(map(int,p)) for p in weapon if np.max(np.abs(p-grip))<=8}
    start=min(nearby,key=lambda p:(np.sum((np.array(p)-grip)**2),p))
    component={start};pending=[start]
    while pending:
        x,y=pending.pop()
        for dx in (-1,0,1):
            for dy in (-1,0,1):
                q=x+dx,y+dy
                if q in nearby and q not in component:component.add(q);pending.append(q)
    away=np.array(grip,dtype=float)-tip;away/=np.linalg.norm(away)
    # End texel of that handle, opposite the blade. Ties favor its shaft axis.
    wp=max(component,key=lambda p:(np.dot(np.array(p)-grip,away),-abs(np.cross(away,np.array(p)-grip)),p))
    bc=np.array(bp,dtype=float)+.5+.5*np.sign(bm.T@direction)
    wc=np.array(wp,dtype=float)+.5-.5*np.sign(wm.T@direction)
    return bc,wc,dict(method='native_hilt_nearest_exposed_body_edge_to_terminal_handle_edge',
        body_pixel=list(bp),weapon_pixel=list(wp),blade_direction=direction.tolist(),
        hand_mask=[list(bp)],handle_component=sorted(map(list,component)),
        body_seed_distance=float(np.linalg.norm(np.array(bp)-seed)))
