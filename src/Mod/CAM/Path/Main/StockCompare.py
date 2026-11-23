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

"""Compare a machined stock solid with the model of a job.

The stock and the model are taken in the same coordinate system, as the stock
and the model of a CAM job are. The comparison uses the Boolean operations and
the distance query that Part already provides; no mesh is built.

The result separates the stock into the material it shares with the model,
the material it still has outside the model (left to cut), and the model
material it no longer has (cut too deep). The sampled deviation reports the
largest distance found from points on one boundary to the other boundary. It
is a sampled maximum, not a bound on the true maximum distance.
"""

from collections import namedtuple

import Path

# lazily loaded modules
from lazy_loader.lazy_loader import LazyLoader

Part = LazyLoader("Part", globals(), "Part")


Deviation = namedtuple("Deviation", ["distance", "point", "nearest", "samples"])
Deviation.__doc__ = """Largest sampled distance from one boundary to another.

distance: the largest distance found, in mm
point:    the sampled point on the source boundary where it was found
nearest:  the closest point on the target boundary to that point
samples:  the number of points sampled on the source boundary"""


class StockComparison:
    """The result of compare(). Volumes are in mm^3, distances in mm."""

    def __init__(self, common, excess, gouge, stockDeviation=None, modelDeviation=None):
        self.common = common
        self.excess = excess
        self.gouge = gouge
        self.stockDeviation = stockDeviation
        self.modelDeviation = modelDeviation

    @property
    def commonVolume(self):
        """Volume of the material shared by the stock and the model."""
        return _volume(self.common)

    @property
    def excessVolume(self):
        """Volume of the stock outside the model, the material left to cut."""
        return _volume(self.excess)

    @property
    def gougeVolume(self):
        """Volume of the model missing from the stock, the material cut too deep."""
        return _volume(self.gouge)


def _volume(shape):
    if shape.isNull() or not shape.Solids:
        return 0.0
    return shape.Volume


def _checkSolid(shape, name):
    if shape is None or shape.isNull():
        raise ValueError(f"{name} shape is null")
    if not shape.Solids:
        raise ValueError(f"{name} shape has no solid")
    if not shape.isValid():
        raise ValueError(f"{name} shape is not valid")


def _facePoints(face, grid):
    """The vertices of the face and the centres of a grid x grid parameter
    raster that lie inside the trimmed face."""
    points = [v.Point for v in face.Vertexes]
    u0, u1, v0, v1 = face.ParameterRange
    for i in range(grid):
        u = u0 + (u1 - u0) * (i + 0.5) / grid
        for j in range(grid):
            v = v0 + (v1 - v0) * (j + 0.5) / grid
            if face.isPartOfDomain(u, v):
                points.append(face.valueAt(u, v))
    return points


def _edgePoints(edge, count):
    first, last = edge.FirstParameter, edge.LastParameter
    if count < 2:
        return [edge.valueAt((first + last) / 2)]
    return [edge.valueAt(first + (last - first) * i / (count - 1)) for i in range(count)]


def sampledDeviation(source, target, faceGrid=7, edgeSamples=17):
    """Return the largest sampled distance from the boundary of source to the
    boundary of target as a Deviation.

    Every face of source is sampled at its vertices and at the centres of a
    faceGrid x faceGrid raster of its parameter range that fall inside the
    trimmed face. Every edge is sampled at edgeSamples evenly spaced
    parameters. Each sample is measured to the faces of target with
    Shape.distToShape().
    """
    if source.isNull() or not source.Faces:
        raise ValueError("source shape has no faces")
    if target.isNull() or not target.Faces:
        raise ValueError("target shape has no faces")

    boundary = Part.makeCompound(target.Faces)
    best = Deviation(-1.0, None, None, 0)
    samples = 0
    for face in source.Faces:
        points = _facePoints(face, faceGrid)
        samples += len(points)
        best = _farthest(points, boundary, best)
    for edge in source.Edges:
        points = _edgePoints(edge, edgeSamples)
        samples += len(points)
        best = _farthest(points, boundary, best)
    return best._replace(samples=samples)


def _farthest(points, boundary, best):
    for point in points:
        distance, pairs, _ = Part.Vertex(point).distToShape(boundary)
        if distance > best.distance:
            nearest = pairs[0][1] if pairs else None
            best = Deviation(distance, point, nearest, best.samples)
    return best


def compare(stock, model, deviation=True, faceGrid=7, edgeSamples=17):
    """Compare the solid stock with the solid model and return a StockComparison.

    stock: the machined stock, for example the result of a simulation
    model: the part the job makes; a compound of several solids is accepted
    deviation: also measure the sampled boundary deviation in both directions
    faceGrid, edgeSamples: the sampling density, see sampledDeviation()
    """
    _checkSolid(stock, "stock")
    _checkSolid(model, "model")

    common = stock.common(model)
    excess = stock.cut(model)
    gouge = model.cut(stock)
    for name, shape in (("common", common), ("excess", excess), ("gouge", gouge)):
        if not shape.isNull() and not shape.isValid():
            raise RuntimeError(f"Boolean operation for the {name} material is not valid")

    result = StockComparison(common, excess, gouge)
    if deviation:
        result.stockDeviation = sampledDeviation(stock, model, faceGrid, edgeSamples)
        result.modelDeviation = sampledDeviation(model, stock, faceGrid, edgeSamples)
    Path.Log.debug(
        f"stock comparison: common {result.commonVolume}, "
        f"excess {result.excessVolume}, gouge {result.gougeVolume}"
    )
    return result
