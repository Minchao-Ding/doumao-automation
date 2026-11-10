"""Geometry compatibility with the existing Phase 2 / original full-grid fixtures."""
import unittest
import cv2
import numpy as np
from doumao.core.gallery_layout import detect_gallery_layout, UnsafeGalleryLayout


def original_full_fixture(occupied=12, cut_bottom=False, offset_x=0):
    image=np.full((1180,1450,3),235,np.uint8)
    ink=(62,62,62)
    xs=[90+offset_x+247*i for i in range(5)]
    ys=[140,460,780,1100]
    for x in xs:cv2.line(image,(x,ys[0]),(x,ys[-1]),ink,2)
    for y in ys:cv2.line(image,(xs[0],y),(xs[-1],y),ink,2)
    for n in range(occupied):
        row,col=divmod(n,4);left,top=xs[col],ys[row]
        x,y=left+124,top+135
        cv2.circle(image,(x,y),67,(45+n*8,73+n*6,210-n*9),-1)
        cv2.rectangle(image,(x-38,y-20),(x+35,y+23),
                      (180-n*3,203-n*8,75+n*7),-1)
        cv2.line(image,(x-30,y+32),(x+27,y-30),ink,5)
    if cut_bottom:image[1040:]=235
    return image


def original_partial_fixture(rows=2, missing=None):
    height,width=956,1470
    image=np.full((height,width,3),(255,250,242),np.uint8)
    xs=[160+220*i for i in range(5)];ys=[360+260*i for i in range(rows+1)]
    ink=(65,70,75)
    for x in xs:cv2.line(image,(x,ys[0]),(x,ys[-1]),ink,2)
    for y in ys:cv2.line(image,(xs[0],y),(xs[-1],y),ink,2)
    for pos in range(rows*4):
        if pos==missing:continue
        row,col=divmod(pos,4);left,top=xs[col],ys[row]
        rng=np.random.default_rng(200+pos)
        cv2.rectangle(image,(left+30,top+40),(left+188,top+190),(150,180,201),-1)
        for _ in range(180):
            x=int(rng.integers(left+50,left+160));y=int(rng.integers(top+48,top+178))
            color=tuple(int(v) for v in rng.integers(12,235,size=3))
            cv2.rectangle(image,(x,y),(x+4,y+4),color,-1)
    return image


class Compatibility(unittest.TestCase):
    def test_original_full(self):
        self.assertEqual(len(detect_gallery_layout(original_full_fixture())),12)

    def test_original_full_horizontal_offset(self):
        self.assertEqual(len(detect_gallery_layout(original_full_fixture(offset_x=120))),12)

    def test_original_partial_one(self):
        self.assertEqual(len(detect_gallery_layout(original_partial_fixture(1))),4)

    def test_original_partial_two(self):
        self.assertEqual(len(detect_gallery_layout(original_partial_fixture(2))),8)

    def test_original_partial_missing(self):
        with self.assertRaises(UnsafeGalleryLayout):
            detect_gallery_layout(original_partial_fixture(2,missing=6))

    def test_original_full_cut_keeps_safely_visible_artwork(self):
        # Changed requirement: a missing caption/bottom border is fine when
        # the thumbnail remains >=75% visible with structural/image evidence.
        self.assertEqual(len(detect_gallery_layout(original_full_fixture(cut_bottom=True))),12)

if __name__=='__main__':unittest.main()
