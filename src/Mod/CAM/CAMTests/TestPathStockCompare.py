# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileCopyrightText: 2026 dylanoliverdo-coder
# SPDX-FileNotice: Part of the FreeCAD project.

################################################################################
#                                                                              #
#   FreeCAD is free software: you can redistribute it and/or modify            #
#   it under the terms of the GNU Lesser General Public License as             #
#   published by the Free Software Foundation, either version 2.1              #
#   of the License, or (at your option) any later version.                     #
#                                                                              #
#   FreeCAD is distributed in the hope that it will be useful,                 #
#   but WITHOUT ANY WARRANTY; without even the implied warranty                #
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.                    #
#   See the GNU Lesser General Public License for more details.                #
#                                                                              #
#   You should have received a copy of the GNU Lesser General Public           #
#   License along with FreeCAD. If not, see https://www.gnu.org/licenses       #
#                                                                              #
################################################################################

import math

import FreeCAD
import Part
import Path.Main.StockCompare as StockCompare

from CAMTests.PathTestUtils import PathTestBase

V = FreeCAD.Vector


class TestPathStockCompare(PathTestBase):
    """Stock against model on simple solids with known results."""

    def setUp(self):
        self.model = Part.makeBox(10, 10, 10)

    def assertBalanced(self, stock, result):
        """Common plus excess is the stock, common plus gouge is the model."""
        self.assertAlmostEqual(result.commonVolume + result.excessVolume, stock.Volume, places=6)
        self.assertAlmostEqual(
            result.commonVolume + result.gougeVolume, self.model.Volume, places=6
        )

    def test00(self):
        """A stock equal to the model has no excess, no gouge and no deviation."""
        stock = self.model.copy()
        result = StockCompare.compare(stock, self.model)

        self.assertAlmostEqual(result.excessVolume, 0, places=6)
        self.assertAlmostEqual(result.gougeVolume, 0, places=6)
        self.assertAlmostEqual(result.commonVolume, 1000, places=6)
        self.assertAlmostEqual(result.stockDeviation.distance, 0, places=6)
        self.assertAlmostEqual(result.modelDeviation.distance, 0, places=6)

    def test01(self):
        """Material left on top of the model is excess, not gouge."""
        stock = Part.makeBox(10, 10, 11)
        result = StockCompare.compare(stock, self.model)

        self.assertAlmostEqual(result.excessVolume, 100, places=6)
        self.assertAlmostEqual(result.gougeVolume, 0, places=6)
        self.assertBalanced(stock, result)
        self.assertTrue(result.excess.isValid())
        self.assertAlmostEqual(result.excess.BoundBox.ZMin, 10, places=6)
        self.assertAlmostEqual(result.excess.BoundBox.ZMax, 11, places=6)

        # the top of the stock is 1 mm above the top of the model
        self.assertAlmostEqual(result.stockDeviation.distance, 1, places=6)
        self.assertAlmostEqual(result.stockDeviation.point.z, 11, places=6)
        self.assertAlmostEqual(result.stockDeviation.nearest.z, 10, places=6)
        self.assertAlmostEqual(result.modelDeviation.distance, 1, places=6)
        self.assertGreater(result.stockDeviation.samples, 0)

    def test02(self):
        """A pocket cut into the model is gouge, not excess."""
        stock = self.model.cut(Part.makeBox(2, 2, 1, V(4, 4, 9)))
        result = StockCompare.compare(stock, self.model)

        self.assertAlmostEqual(result.excessVolume, 0, places=6)
        self.assertAlmostEqual(result.gougeVolume, 4, places=6)
        self.assertBalanced(stock, result)
        self.assertAlmostEqual(result.gouge.BoundBox.XMin, 4, places=6)
        self.assertAlmostEqual(result.gouge.BoundBox.XMax, 6, places=6)
        self.assertAlmostEqual(result.gouge.BoundBox.ZMin, 9, places=6)

        # the centre of the model's top face lies 1 mm from the pocket floor and walls
        self.assertAlmostEqual(result.modelDeviation.distance, 1, places=6)
        self.assertAlmostEqual(result.modelDeviation.point.x, 5, places=6)
        self.assertAlmostEqual(result.modelDeviation.point.y, 5, places=6)
        self.assertAlmostEqual(result.modelDeviation.point.z, 10, places=6)

    def test03(self):
        """A round hole cut into the model is measured on its curved faces."""
        hole = Part.makeCylinder(1, 3, V(5, 5, 7))
        stock = self.model.cut(hole)
        result = StockCompare.compare(stock, self.model)

        self.assertAlmostEqual(result.excessVolume, 0, places=6)
        self.assertAlmostEqual(result.gougeVolume, math.pi * 3, places=6)
        self.assertBalanced(stock, result)

        # the floor of the hole is 3 mm below the top of the model
        self.assertAlmostEqual(result.stockDeviation.distance, 3, places=6)
        self.assertAlmostEqual(result.stockDeviation.point.z, 7, places=6)

    def test04(self):
        """Excess and gouge are found together, and deviation can be skipped."""
        stock = Part.makeBox(10, 10, 11).cut(Part.makeBox(2, 2, 2, V(4, 4, 9)))
        result = StockCompare.compare(stock, self.model, deviation=False)

        # 100 mm^3 on top less the 4 mm^3 of the pocket above the model
        self.assertAlmostEqual(result.excessVolume, 96, places=6)
        self.assertAlmostEqual(result.gougeVolume, 4, places=6)
        self.assertBalanced(stock, result)
        self.assertIsNone(result.stockDeviation)
        self.assertIsNone(result.modelDeviation)

    def test05(self):
        """A model made of several solids is compared as a whole."""
        second = Part.makeBox(10, 10, 10, V(20, 0, 0))
        self.model = Part.makeCompound([self.model, second])
        stock = Part.makeBox(30, 10, 10)
        result = StockCompare.compare(stock, self.model, deviation=False)

        self.assertAlmostEqual(result.excessVolume, 1000, places=6)
        self.assertAlmostEqual(result.gougeVolume, 0, places=6)
        self.assertBalanced(stock, result)

    def test06(self):
        """Shapes without a solid are refused."""
        face = Part.makePlane(10, 10)
        with self.assertRaises(ValueError):
            StockCompare.compare(face, self.model)
        with self.assertRaises(ValueError):
            StockCompare.compare(self.model, Part.Shape())
