from gf import GfTwoRealTime_cython, MeshTwoRealTime, MeshReTime, TailGf
from gf_generic import GfGeneric
import numpy
from tools import get_indices_in_dict
import impl_plot

class GfTwoRealTime( GfGeneric, GfTwoRealTime_cython ) :
    def __init__(self, **d):
        """
        The constructor have two variants : you can either provide the mesh in
        Matsubara frequencies yourself, or give the parameters to build it.
        All parameters must be given with keyword arguments.

        GfTwoRealTime(indices, window, n_points, data, tail, name)

              * ``indices``:  a list of indices names of the block
              * ``window``:  a tuple (t_min, t_max)
              * ``n_points``  : Number of time points in the mesh
              * ``data``:   A numpy array of dimensions (len(indices),len(indices),n_points) representing the value of the Green function on the mesh.
              * ``tail``:  the tail
              * ``name``:  a name of the GF

        GfReTime (indices, mesh, data, tail, name)

              * ``indices``:  a list of indices names of the block
              * ``mesh``:  a MeshGf object, such that mesh.TypeGF== GF_Type.Imaginary_Time
              * ``data``:   A numpy array of dimensions (len(indices),len(indices),n_points) representing the value of the Green function on the mesh.
              * ``tail``:  the tail
              * ``name``:  a name of the GF

        .. warning::

          The Green function take a **view** of the array data, and a **reference** to the tail.

        """
        mesh = d.pop('mesh',None)
        if mesh is None :
            window = d.pop('window')
            t_min = window[0]
            t_max = window[1]
            n_max = d.pop('n_points',10000)
            kind = d.pop('kind','F')
            mesh = MeshTwoRealTime(t_max, n_max)
            #mesh = MeshTwoRealTime(t_min, t_max, n_max)
            #mesh = MeshReTime(t_min, t_max, n_max, 'F')

        self.dtype = numpy.complex_
        indices_pack = get_indices_in_dict(d)
        indicesL, indicesR = indices_pack
        N1, N2 = len(indicesL),len(indicesR)
        data = d.pop('data') if 'data' in d else numpy.zeros((len(mesh),N1,N2), self.dtype )
        symmetry = d.pop('symmetry',None)
        name = d.pop('name','g')
        assert len(d) ==0, "Unknown parameters in GfTwoRealTime constructions %s"%d.keys()

        GfGeneric.__init__(self, mesh, data, None, symmetry, indices_pack, name, GfTwoRealTime)
        GfTwoRealTime_cython.__init__(self, mesh, data)

    #--------------   PLOT   ---------------------------------------

    def _plot_(self, opt_dict):
        """ Plot protocol. opt_dict can contain :
             * :param RI: 'R', 'I', 'RI' [ default]
             * :param x_window: (xmin,xmax) or None [default]
             * :param name: a string [default ='']. If not '', it remplaces the name of the function just for this plot.
        """
        # NOT CHANGED
        return impl_plot.plot_base(self, opt_dict,  r'$\t$', lambda name : r'%s$(\t)$'%name, True, list(self.mesh))
