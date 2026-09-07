"""Native pixel projection, local edge separation and CPU raster review helpers."""
import math
import numpy as np
from PIL import Image

def affine(geometry, dimensions):
    top,left,bottom,right,angle=geometry;w,h=dimensions;a=math.radians(angle)
    rotation=np.array([[math.cos(a),-math.sin(a)],[math.sin(a),math.cos(a)]])
    matrix=rotation@np.diag([(right-left)/w,(bottom-top)/h])
    center=np.array([(left+right)/2,(top+bottom)/2])
    origin=center-matrix@np.array([w/2,h/2])
    return origin,matrix

def vertices(center,matrix):
    return center+np.array([[-.5,-.5],[.5,-.5],[.5,.5],[-.5,.5]])@matrix.T

def solve(body_points,body_matrix,weapon_points,weapon_matrix,axis):
    # Pixel rectangles have just four distinct separating axes.
    normals=np.array([[1.,0.],[0.,1.],weapon_matrix[:,0]/np.linalg.norm(weapon_matrix[:,0]),
                      weapon_matrix[:,1]/np.linalg.norm(weapon_matrix[:,1])])
    aa=body_points@normals.T;bb=weapon_points@normals.T
    ah=np.abs(normals@body_matrix).sum(axis=1)/2
    bh=np.abs(normals@weapon_matrix).sum(axis=1)/2
    delta=aa[:,None,:]-bb[None,:,:];extent=ah+bh
    speed=normals@axis
    lows=np.full(delta.shape,-np.inf);highs=np.full(delta.shape,np.inf)
    for n,s in enumerate(speed):
        if abs(s)<1e-10:
            invalid=np.abs(delta[:,:,n])>=extent[n]-1e-9
            lows[:,:,n][invalid]=np.inf;highs[:,:,n][invalid]=-np.inf
        else:
            x=(delta[:,:,n]-extent[n])/s;y=(delta[:,:,n]+extent[n])/s
            lows[:,:,n]=np.minimum(x,y);highs[:,:,n]=np.maximum(x,y)
    low=lows.max(axis=2);high=highs.min(axis=2)
    valid=(high>np.maximum(low,0)+1e-8)
    overlap=((low<0)&(high>0)&valid)
    assert overlap.any(), 'Expected current palm/weapon overlap for this contact measurement'
    # End of the collision interval connected to the initial overlapping pose.
    end=0.;chosen=None
    while True:
        connected=valid&(low<=end+1e-8)
        index=np.unravel_index(np.argmax(np.where(connected,high,-np.inf)),high.shape)
        candidate=float(high[index])
        if candidate<=end+1e-8:break
        end=candidate;chosen=index
    ai,bi=chosen;ni=int(np.argmin(highs[ai,bi]));normal=normals[ni]
    if speed[ni]<0:normal=-normal
    av=vertices(body_points[ai],body_matrix)
    bv=vertices(weapon_points[bi]+axis*end,weapon_matrix)
    plane=float((av@normal).max());plane2=float((bv@normal).min())
    assert abs(plane-plane2)<1e-5
    tangent=np.array([-normal[1],normal[0]])
    sa=av[np.abs(av@normal-plane)<1e-5]@tangent
    sb=bv[np.abs(bv@normal-plane2)<1e-5]@tangent
    lo=max(sa.min(),sb.min());hi=min(sa.max(),sb.max())
    assert lo<=hi+1e-5
    contact=normal*plane+tangent*((lo+hi)/2)
    assert not np.any(valid&(low<end-1e-6)&(high>end+1e-6))
    return contact,end,dict(initial_intersecting_pixel_pairs=int(overlap.sum()),
                            boundary_body_pixel=int(ai),boundary_weapon_pixel=int(bi),
                            body_normal=normal.tolist())

def penetration(a,am,b,bm):
    normals=np.array([v/np.linalg.norm(v) for v in (am[:,0],am[:,1],bm[:,0],bm[:,1])])
    half=(np.abs(normals@am).sum(axis=1)+np.abs(normals@bm).sum(axis=1))/2
    delta=np.abs((a@normals.T)[:,None,:]-(b@normals.T)[None,:,:])
    return float(np.maximum(0,np.min(half-delta,axis=2)).max())

def paint(canvas,im,g,scale=3,origin=(60,85)):
    top,left,bottom,right,degrees=g;w,h=im.size
    angle=math.radians(degrees);c,s=math.cos(angle),math.sin(angle)
    cx,cy=(left+right)/2,(top+bottom)/2
    wx,wy=w/(right-left),h/(bottom-top)
    # Output board pixels -> actor-local coordinates -> inverse packet quad.
    tx,ty=400-origin[0]-cx,300-origin[1]-cy
    coeff=(c*wx/scale,s*wx/scale,w/2+wx*(c*tx+s*ty),
           -s*wy/scale,c*wy/scale,h/2+wy*(-s*tx+c*ty))
    layer=im.transform(canvas.size,Image.Transform.AFFINE,coeff,resample=Image.Resampling.NEAREST)
    canvas.alpha_composite(layer)
