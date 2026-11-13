"""Motion-compensated silhouette interpolation; no RGB ghost-image crossfade.

Only the offline asset tools require OpenCV/NumPy/SciPy. Host playback uses PNGs.
"""
import cv2
import numpy as np
from scipy import ndimage
from PIL import Image


def _alpha(image):
    return np.asarray(image.convert('RGBA').getchannel('A'), dtype=np.float32)/255


def _flow(a, b):
    # Register distance fields, not textureless hairline strokes: broad spatial
    # support prevents opposing edges from tearing a thin limb in two.
    def field(alpha):
        return np.clip(128+_distance(alpha)*4,0,255).astype('uint8')
    a,b=field(a),field(b)
    flow=cv2.calcOpticalFlowFarneback(a,b,None,.5,5,31,7,7,1.5,0)
    return cv2.GaussianBlur(flow,(0,0),1.2)


def _warp(alpha, flow, amount):
    y,x=np.indices(alpha.shape,dtype=np.float32)
    return cv2.remap(alpha,x-flow[:,:,0]*amount,y-flow[:,:,1]*amount,
                     cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT)


def _distance(alpha):
    mask=alpha>.4
    return ndimage.distance_transform_edt(mask)-ndimage.distance_transform_edt(~mask)


def _colored(alpha, template):
    rgba=np.asarray(template.convert('RGBA'))
    pixels=rgba[:,:,:3][rgba[:,:,3]>200]
    color=tuple(np.median(pixels,axis=0).astype('uint8')) if len(pixels) else (255,255,255)
    result=Image.new('RGBA',template.size,(*color,0))
    # Signed-distance reconstruction yields a single antialiased contour.
    result.putalpha(Image.fromarray(np.clip(alpha*255,0,255).astype('uint8')))
    return result


def tween(a,b,t):
    """Keep source endpoints exact; interpolate motion and then the contour."""
    if t<=0:return a.copy()
    if t>=1:return b.copy()
    aa,bb=_alpha(a),_alpha(b)
    if np.array_equal(aa,bb):return a.copy()
    forward,backward=_flow(aa,bb),_flow(bb,aa)
    wa=_warp(aa,forward,t);wb=_warp(bb,backward,1-t)
    # Warp the nearest original silhouette instead of intersecting two signed
    # fields. Intersection-style morphing can amputate a thin moving limb.
    alpha=wa if t<=.5 else wb
    source=aa if t<=.5 else bb
    ratio=alpha.sum()/max(source.sum(),1)
    if not .8<=ratio<=1.2:
        alpha=source
    return _colored(alpha,a if t<=.5 else b)


def stabilize(images, strength=.15):
    """Suppress mask chatter with neighbours warped into the current pose.

    Does not loop a one-shot action or blend its ending into its beginning.
    First/last source poses are retained exactly.
    """
    if not 0<=strength<=.25:raise ValueError('strength must be between 0 and .25')
    result=[]
    for i,image in enumerate(images):
        if i in (0,len(images)-1):
            result.append(image.copy());continue
        current=_alpha(image);field=_distance(current)*(1-2*strength)
        for other in (images[i-1],images[i+1]):
            neighbor=_alpha(other)
            aligned=_warp(neighbor,_flow(neighbor,current),1)
            field+=strength*_distance(aligned)
        # Never let a failed correspondence erase a thin hand/foot or inflate
        # the body. Limit contour displacement, then retain the source if its
        # total silhouette coverage would change by more than ten percent.
        original_field=_distance(current)
        field=np.clip(field,original_field-.6,original_field+.6)
        alpha=np.clip(field*.75+.5,0,1)
        ratio=alpha.sum()/max(current.sum(),1)
        result.append(_colored(alpha,image) if .9<=ratio<=1.1 else image.copy())
    return result
