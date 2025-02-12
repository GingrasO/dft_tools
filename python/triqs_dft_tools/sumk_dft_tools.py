##########################################################################
#
# TRIQS: a Toolbox for Research in Interacting Quantum Systems
#
# Copyright (C) 2011 by M. Aichhorn, L. Pourovskii, V. Vildosola
#
# TRIQS is free software: you can redistribute it and/or modify it under the
# terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.
#
# TRIQS is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
# details.
#
# You should have received a copy of the GNU General Public License along with
# TRIQS. If not, see <http://www.gnu.org/licenses/>.
#
##########################################################################
"""
Extension to the SumkDFT class with some analyiss tools
"""

import sys
from types import *
import numpy
from triqs.gf import *
import triqs.utility.mpi as mpi
from .symmetry import *
from .sumk_dft import SumkDFT
from scipy.integrate import *
from scipy.interpolate import *

if not hasattr(numpy, 'full'):
    # polyfill full for older numpy:
    numpy.full = lambda a, f: numpy.zeros(a) + f

class SumkDFTTools(SumkDFT):
    """
    Extends the SumkDFT class with some tools for analysing the data.
    """

    def __init__(self, hdf_file, h_field=0.0, mesh=None, beta=40, n_iw=1025, use_dft_blocks=False, dft_data='dft_input', symmcorr_data='dft_symmcorr_input',
                 parproj_data='dft_parproj_input', symmpar_data='dft_symmpar_input', bands_data='dft_bands_input',
                 transp_data='dft_transp_input', misc_data='dft_misc_input', cont_data='dft_contours_input'):
        """
        Initialisation of the class. Parameters are exactly as for SumKDFT.
        """

        SumkDFT.__init__(self, hdf_file=hdf_file, h_field=h_field, mesh=mesh, beta=beta, n_iw=n_iw,
                        use_dft_blocks=use_dft_blocks, dft_data=dft_data, symmcorr_data=symmcorr_data,
                        parproj_data=parproj_data, symmpar_data=symmpar_data, bands_data=bands_data,
                        transp_data=transp_data, misc_data=misc_data, cont_data=cont_data)

    def density_of_states(self, mu=None, broadening=None, mesh=None, with_Sigma=True, with_dc=True, proj_type=None, dosocc=False, save_to_file=True):
        """
        Calculates the density of states and the projected density of states.
        The basis of the projected density of states is specified by proj_type.

        The output files (if `save_to_file = True`) have two (three in the orbital-resolved case) columns representing the frequency and real part of the DOS (and imaginary part of the DOS) in that order. 

        The output files are as follows:

        - DOS_(spn).dat, the total DOS.
        - DOS_(proj_type)_(spn)_proj(i).dat, the DOS projected to an orbital with index i which refers to the index given in SK.shells (or SK.corr_shells for proj_type = "wann").
        - DOS_(proj_type)_(sp)_proj(i)_(m)_(n).dat, As above, but printed as orbitally-resolved matrix in indices "m" and "n". For example, for "d" orbitals, it gives the DOS separately for each orbital (e.g., `d_(xy)`, `d_(x^2-y^2)`, and so on).

        Parameters
        ----------
        mu           : double, optional
                       Chemical potential, overrides the one stored in the hdf5 archive.
                       By default, this is automatically set to the chemical potential within the SK object.
        broadening   : double, optional
                       Lorentzian broadening of the spectra to avoid any numerical artifacts.
                       If not given, standard value of lattice_gf (0.001 eV) is used.
        mesh         : real frequency MeshType, optional
                       Omega mesh for the real-frequency Green's function. 
                       Given as parameter to lattice_gf.
        with_Sigma   : boolean, optional
                       If True, the self energy is used for the calculation. 
                       If false, the DOS is calculated without self energy.
                       Both with_Sigma and with_dc equal to True is needed for DFT+DMFT A(w) calculated. 
                       Both with_Sigma and with_dc equal to false is needed for DFT A(w) calculated.
        with_dc      : boolean, optional
                       If True the double counting correction is used.
        proj_type     : string, optional
                        The type of projection used for the orbital-projected DOS.
                        These projected spectral functions will be determined alongside the total spectral function.
                        By default, no projected DOS type will be calculated (the corresponding projected arrays will be empty).
                        The following options are:

                       'None'   - Only total DOS calculated 
                       'wann'   - Wannier DOS calculated from the Wannier projectors
                       'vasp'   - Vasp orbital-projected DOS only from Vasp inputs
                       'wien2k' - Wien2k orbital-projected DOS from the wien2k theta projectors
        dosocc       : boolean, optional
                       If True, the occupied DOS, DOSproj and DOSproj_orb will be returned.
                       The prerequisite of this option is to have calculated the band-resolved
                       density matrices generated by the occupations() routine.
        save_to_file : boolean, optional
                       If True, text files with the calculated data will be created.

        Returns
        -------
        DOS          : Dict of numpy arrays
                       Contains the full density of states with the form of DOS[spn][n_om] where "spn" speficies the spin type of the calculation ("up", "down", or combined "ud" which relates to calculations with spin-orbit coupling) and "n_om" is the number of real frequencies as specified by the real frequency MeshType used in the calculation. This array gives the total density of states.
        DOSproj      : Dict of numpy arrays
                       DOS projected to atom (shell) with the form of DOSproj[n_shells][spn][n_om] where "n_shells" is the total number of correlated or uncorrelated shells (depending on the input "proj_type"). This array gives the trace of the orbital-projected density of states. Empty if proj_type = None
        DOSproj_orb  : Dict of numpy arrays
                       Orbital-projected DOS projected to atom (shell) and resolved into orbital contributions with the form of DOSproj_orb[n_shells][spn][n_om,dim,dim] where "dim" specifies the orbital dimension of the correlated/uncorrelated shell (depending on the input "proj_type"). 
                       Empty if proj_type = None
        """

        # Note the proj_type = 'elk'  (- Elk orbital-projected DOS only from Elk inputs) is not included for now. 
        # Brief description to why can be found in the comment above the currently commented out dft_band_characters() routine
        # in converters/elk.py.
        # code left here just in case it will be reused.
        if (proj_type != None):
            # assert proj_type in ('wann', 'vasp','wien2k','elk'), "'proj_type' must be either 'wann', 'vasp', 'wien2k', or 'elk'"
            assert proj_type in ('wann', 'vasp', 'wien2k',
                                 ), "'proj_type' must be either 'wann', 'vasp', 'wien2k'"
            if (proj_type != 'wann'):
                assert proj_type == self.dft_code, "proj_type must be from the corresponding dft inputs."

        if (with_Sigma):
            assert isinstance(
                self.Sigma_imp[0].mesh, MeshReFreq), "SumkDFT.mesh must be real if with_Sigma is True"
            mesh = self.Sigma_imp[0].mesh
        elif mesh is not None:
            assert isinstance(mesh, MeshReFreq), "mesh must be of form MeshReFreq"
            if broadening is None:
                broadening = 0.001
        elif self.mesh is not None:
            assert isinstance(self.mesh, MeshReFreq), "self.mesh must be of form MeshReFreq"
            mesh = self.mesh
            if broadening is None:
                broadening = 0.001
        else:
            assert 0, "ReFreqMesh input required for calculations without real frequency self-energy"
        mesh_val = numpy.linspace(mesh.w_min, mesh.w_max, len(mesh))
        n_om = len(mesh)
        om_minplot = mesh_val[0] - 0.001
        om_maxplot = mesh_val[-1] + 0.001

        # Read in occupations from HDF5 file if required
        if (dosocc):
            mpi.report('Reading occupations generated by self.occupations().')
            thingstoread = ['occik']
            subgroup_present, values_not_read = self.read_input_from_hdf(
                subgrp=self.misc_data, things_to_read=thingstoread)
            if len(values_not_read) > 0 and mpi.is_master_node:
                raise ValueError(
                       'ERROR: One or more necessary SumK input properties have not been found in the given h5 archive:', self.values_not_read)

        # initialise projected DOS type if required
        spn = self.spin_block_names[self.SO]
        n_shells = 1
        if (proj_type == 'wann'):
            n_shells = self.n_corr_shells
            gf_struct = self.gf_struct_sumk.copy()
            dims = [self.corr_shells[ish]['dim'] for ish in range(n_shells)]
            shells_type = 'corr'
        elif (proj_type == 'vasp'):
            n_shells = 1
            gf_struct = [[(sp, list(range(self.proj_mat_csc.shape[2]))) for sp in spn]]
            dims = [self.proj_mat_csc.shape[2]]
            shells_type = 'csc'
        elif (proj_type == 'wien2k'):
            self.load_parproj()
            n_shells = self.n_shells
            gf_struct = [[(sp, self.shells[ish]['dim']) for sp in spn]
                         for ish in range(n_shells)]
            dims = [self.shells[ish]['dim'] for ish in range(n_shells)]
            shells_type = 'all'
# #commented out for now - unsure this produces DFT+DMFT PDOS
#        elif (proj_type == 'elk'):
#            n_shells = self.n_shells
#            dims = [self.shells[ish]['dim'] for ish in range(n_shells)]
#            gf_struct = [[(sp, self.shells[ish]['dim']) for sp in spn]
#                             for ish in range(n_shells)]
#            things_to_read = ['band_dens_muffin']
#            subgroup_present, values_not_read =  self.read_input_from_hdf(
#                           subgrp=self.bc_data, things_to_read=things_to_read)
#            if len(values_not_read) > 0 and mpi.is_master_node:
#                raise ValueError(
#                'ERROR: One or more necessary SumK input properties have not been found in the given h5 archive:', self.values_not_read)

        # set-up output arrays
        DOS = {sp: numpy.zeros([n_om], float) for sp in spn}
        DOSproj = [{} for ish in range(n_shells)]
        DOSproj_orb = [{} for ish in range(n_shells)]
        # set-up Green's function object
        if (proj_type != None):
          G_loc = []
          for ish in range(n_shells):
              glist = [GfReFreq(target_shape=(block_dim, block_dim), mesh=mesh)
                       for block, block_dim in gf_struct[ish]]
              G_loc.append(
                  BlockGf(name_list=spn, block_list=glist, make_copies=False))
              G_loc[ish].zero()
              dim = dims[ish]
              for sp in spn:
                  DOSproj[ish][sp] = numpy.zeros([n_om], float)
                  DOSproj_orb[ish][sp] = numpy.zeros(
                      [n_om, dim, dim], complex)

        # calculate the DOS
        ikarray = numpy.array(list(range(self.n_k)))
        for ik in mpi.slice_array(ikarray):
            G_latt_w = self.lattice_gf(
                ik=ik, mu=mu, broadening=broadening, mesh=mesh, with_Sigma=with_Sigma, with_dc=with_dc)
            G_latt_w *= self.bz_weights[ik]
            # output occupied DOS if nk inputted
            if (dosocc):
              for bname, gf in G_latt_w:
                G_latt_w[bname].data[:, :, :] *= self.occik[bname][ik]
            # DOS
            for bname, gf in G_latt_w:
                DOS[bname] -= gf.data.imag.trace(axis1=1, axis2=2)/numpy.pi
            # Projected DOS:
            if (proj_type != None):
                for ish in range(n_shells):
                    tmp = G_loc[ish].copy()
                    tmp.zero()
                    tmp << self.proj_type_G_loc(G_latt_w, tmp, ik, ish, proj_type)
                    G_loc[ish] += tmp
        mpi.barrier()

        # Collect data from mpi:
        for bname in DOS:
            DOS[bname] = mpi.all_reduce(DOS[bname])
        # Collect data from mpi and put in projected arrays
        if (proj_type != None):
          for ish in range(n_shells):
              G_loc[ish] << mpi.all_reduce(G_loc[ish])
        # Symmetrize and rotate to local coord. system if needed:
          if ((proj_type != 'vasp') and (proj_type != 'elk')):
            if self.symm_op != 0:
                if proj_type == 'wann':
                    G_loc = self.symmcorr.symmetrize(G_loc)
                else:
                    G_loc = self.symmpar.symmetrize(G_loc)
            if self.use_rotations:
                for ish in range(n_shells):
                    for bname, gf in G_loc[ish]:
                        G_loc[ish][bname] << self.rotloc(
                            ish, gf, direction='toLocal', shells=shells_type)
        # G_loc can now also be used to look at orbitally-resolved quantities
          for ish in range(n_shells):
            for bname, gf in G_loc[ish]:  # loop over spins
                DOSproj[ish][bname] = -gf.data.imag.trace(axis1=1, axis2=2) / numpy.pi
                DOSproj_orb[ish][bname][
                    :, :, :] += (1.0j*(gf-gf.conjugate().transpose())/2.0/numpy.pi).data[:, :, :]

        # Write to files
        if save_to_file and mpi.is_master_node():
            for sp in spn:
                f = open('DOS_%s.dat' % sp, 'w')
                for iom in range(n_om):
                    f.write("%s    %s\n" % (mesh_val[iom], DOS[sp][iom]))
                f.close()
                # Partial
                if (proj_type != None):
                  for ish in range(n_shells):
                    f = open('DOS_' + proj_type + '_%s_proj%s.dat' % (sp, ish), 'w')
                    for iom in range(n_om):
                        f.write("%s    %s\n" %
                                (mesh_val[iom], DOSproj[ish][sp][iom]))
                    f.close()
                    # Orbitally-resolved
                    for i in range(dims[ish]):
                        for j in range(dims[ish]):
                            # For Elk with parproj - skip off-diagonal elements
                            # if(proj_type=='elk') and (i!=j): continue
                            f = open('DOS_' + proj_type + '_' + sp + '_proj' + str(ish) +
                                     '_' + str(i) + '_' + str(j) + '.dat', 'w')
                            for iom in range(n_om):
                                f.write("%s    %s    %s\n" % (
                                    mesh_val[iom], DOSproj_orb[ish][sp][iom, i, j].real, DOSproj_orb[ish][sp][iom, i, j].imag))
                            f.close()

        return DOS, DOSproj, DOSproj_orb

    def proj_type_G_loc(self, G_latt, G_inp, ik, ish, proj_type=None):
        """
        Internal routine which calculates the project Green's function subject to the 
        proj_type input.

        Parameters
        ----------
        G_latt   : Gf
                   block of lattice Green's functions to be projected/downfolded
        G_inp    : Gf
                   block of local Green's functions used as a template for G_proj
        ik       : integer
                   integer specifing k-point index.
        ish      : integer
                   integer specifing shell index.
        proj_type : string, optional
                   Output the orbital-projected DOS type from the following options:
                   'wann'   - Wannier DOS calculated from the Wannier projectors
                   'vasp'   - Vasp orbital-projected DOS only from Vasp inputs
                   'wien2k' - Wien2k orbital-projected DOS from the wien2k theta projectors
                   
        Returns
        -------
        G_proj   : Gf
                   projected/downfolded lattice Green's function
                   Contains the band-resolved density matrices per k-point.
        """

        # Note the proj_type = 'elk'  (- Elk orbital-projected DOS only from Elk inputs) is not included for now. 
        # Brief description to why can be found in the comment above the currently commented out dft_band_characters() routine
        # in converters/elk.py.
        # code left here just in case it will be reused.
        G_proj = G_inp.copy()
        if (proj_type == 'wann'):
           for bname, gf in G_proj:
              G_proj[bname] << self.downfold(ik, ish, bname,
                                             G_latt[bname], gf)  # downfolding G
        elif (proj_type == 'vasp'):
           for bname, gf in G_latt:
              G_proj[bname] << self.downfold(ik, ish, bname, gf, G_proj[bname], shells='csc')
        elif (proj_type == 'wien2k'):
           tmp = G_proj.copy()
           for ir in range(self.n_parproj[ish]):
              tmp.zero()
              for bname, gf in tmp:
                 tmp[bname] << self.downfold(ik, ish, bname,
                                             G_latt[bname], gf, shells='all', ir=ir)
              G_proj += tmp
#        elif (proj_type == 'elk'):
#           dim = self.shells[ish]['dim']
#           ntoi = self.spin_names_to_ind[self.SO]
#           for bname, gf in G_latt:
#              n_om = len(gf.data[:,0,0])
#              isp=ntoi[bname]
#              nst=self.n_orbitals[ik,isp]
#              #matrix multiply band resolved muffin density with
#              #diagonal of band resolved spectral function and fill diagonal of 
#              #DOSproj_orb orbital dimensions with the result for each frequency
#              bdm=self.band_dens_muffin[ik,isp,ish,0:dim,0:nst]
#              tmp=[numpy.matmul(bdm, gf.data[iom,:,:].diagonal())
#                         for iom in range(n_om)]
#              tmp=numpy.asarray(tmp)
#              tmp2 = numpy.zeros([n_om,dim,dim], dtype=complex)
#              if(dim==1):
#                  tmp2[:,0,0]=tmp[:,0]
#              else:
#                 [numpy.fill_diagonal(tmp2[iom,:,:],tmp[iom,:])
#                         for iom in range(n_om)]
#              G_proj[bname].data[:,:,:] = tmp2[:,:,:]

        return G_proj

    def load_parproj(self, data_type=None):
        """
        Internal routine which loads the n_parproj, proj_mat_all, rot_mat_all and 
        rot_mat_all_time_inv from parproj data from .h5 file.

        Parameters
        ----------
        data_type : string, optional
                    which data type desired to be read in. 
                    'band' - reads data converted by bands_convert()        
                    None - reads data converted by parproj_convert()
        """

        # read in the projectors
        things_to_read = ['n_parproj', 'proj_mat_all']
        if data_type == 'band':
            subgroup_present, values_not_read = self.read_input_from_hdf(
                subgrp=self.bands_data, things_to_read=things_to_read)
        else:
            subgroup_present, values_not_read = self.read_input_from_hdf(
                subgrp=self.parproj_data, things_to_read=things_to_read)
            if self.symm_op:
                self.symmpar = Symmetry(self.hdf_file, subgroup=self.symmpar_data)
        if len(values_not_read) > 0 and mpi.is_master_node:
            raise ValueError(
                'ERROR: One or more necessary SumK input properties have not been found in the given h5 archive:', self.values_not_read)
        # read general data
        things_to_read = ['rot_mat_all', 'rot_mat_all_time_inv']
        subgroup_present, values_not_read = self.read_input_from_hdf(
            subgrp=self.parproj_data, things_to_read=things_to_read)
        if len(values_not_read) > 0 and mpi.is_master_node:
            raise ValueError(
                'ERROR: One or more necessary SumK input properties have not been found in the given h5 archive:', self.values_not_read)

    def occupations(self, mu=None, with_Sigma=True, with_dc=True, save_occ=True):
        """
        Calculates the band resolved density matrices (occupations) from the Matsubara 
        frequency self-energy.

        Parameters
        ----------
        mu           : double, optional
                       Chemical potential, overrides the one stored in the hdf5 archive.
        with_Sigma   : boolean, optional
                       If True, the self energy is used for the calculation. 
                       If false, the DOS is calculated without self energy.
        with_dc      : boolean, optional
                       If True the double counting correction is used.
        save_occ     : boolean, optional
                       If True, saves the band resolved density matrix in misc_data.
        save_to_file : boolean, optional
                       If True, text files with the calculated data will be created.

        Returns
        -------
        occik        : Dict of numpy arrays
                       Contains the band-resolved density matrices per k-point.
        """

        if with_Sigma:
            mesh = self.Sigma_imp[0].mesh
        else:
            mesh = self.mesh
        assert isinstance(
            mesh, MeshImFreq), "SumkDFT.mesh must be real if with_Sigma is True or mesh is not given"

        if mu is None:
            mu = self.chemical_potential
        ntoi = self.spin_names_to_ind[self.SO]
        spn = self.spin_block_names[self.SO]
        occik = {}
        for sp in spn:
          # same format as gf.data ndarray
          occik[sp] = [numpy.zeros([1, self.n_orbitals[ik, ntoi[sp]],
                                   self.n_orbitals[ik, ntoi[sp]]], numpy.double) for ik in range(self.n_k)]
        # calculate the occupations
        ikarray = numpy.array(range(self.n_k))
        for ik in range(self.n_k):
          G_latt = self.lattice_gf(
              ik=ik, mu=mu, with_Sigma=with_Sigma, with_dc=with_dc)
          for bname, gf in G_latt:
            occik[bname][ik][0, :, :] = gf.density().real
        # Collect data from mpi:
        for sp in spn:
          occik[sp] = mpi.all_reduce(occik[sp])
        mpi.barrier()
        # save to HDF5 file (if specified)
        if save_occ and mpi.is_master_node():
          things_to_save_misc = ['occik']
          # Save it to the HDF:
          ar = HDFArchive(self.hdf_file, 'a')
          if not (self.misc_data in ar):
            ar.create_group(self.misc_data)
          for it in things_to_save_misc:
            ar[self.misc_data][it] = locals()[it]
          del ar
        return occik

    def spectral_contours(self, mu=None, broadening=None, mesh=None, plot_range=None, FS=True, with_Sigma=True, with_dc=True, proj_type=None, save_to_file=True):
        """
        Calculates the correlated spectral function at the Fermi level (relating to the Fermi
        surface) or at specific frequencies. 

        The output files have three columns representing the k-point index, frequency and A(k,w) in that order. The output files are as follows:

        * `Akw_(sp).dat`, the total A(k,w)
        * `Akw_(proj_type)_(spn)_proj(i).dat`, the A(k,w) projected to shell with index (i).
        * `Akw_(proj_type)_(spn)_proj(i)_(m)_(n).dat`, as above, but for each (m) and (n) orbital contribution.
        
        The files are prepended with either of the following: 
        For `FS` set to True the output files name include _FS_ and these files contain four columns which are the cartesian reciprocal coordinates (kx, ky, kz) and Akw. 
        For `FS` set to False the output files name include _omega_(iom) (with `iom` being the frequency mesh index). These files also contain four columns  as described above along with a comment at the top of the file which gives the frequency value at which the spectral function was evaluated.

        Parameters
        ----------
        mu           : double, optional
                       Chemical potential, overrides the one stored in the hdf5 archive.
                       By default, this is automatically set to the chemical potential within the SK object.
        broadening   : double, optional
                       Lorentzian broadening of the spectra to avoid any numerical artifacts.
                       If not given, standard value of lattice_gf (0.001 eV) is used.
        mesh         : real frequency MeshType, optional
                       Omega mesh for the real-frequency Green's function. 
                       Given as parameter to lattice_gf.
        plot_shift   : double, optional
                       Offset [=(ik-1)*plot_shift, where ik is the index of the k-point] for each A(k,w) for stacked plotting of spectra.
        plot_range   : list of double, optional
                       Sets the energy window for plotting to (plot_range[0],plot_range[1]).
                       If not provided, the min and max values of the energy mesh is used.
        FS           : boolean
                       Flag for calculating the spectral function at the Fermi level (omega ~ 0)
                       If False, the spectral function will be generated for each frequency within 
                       plot_range.              
        with_Sigma   : boolean, optional
                       If True, the self energy is used for the calculation. 
                       If false, the DOS is calculated without self energy.
                       Both with_Sigma and with_dc equal to True is needed for DFT+DMFT A(k,w) calculated. 
                       Both with_Sigma and with_dc equal to false is needed for DFT A(k,w) calculated.
        with_dc      : boolean, optional
                       If True the double counting correction is used.
        proj_type    : string, optional
                       The type of projection used for the orbital-projected DOS.
                       These projected spectral functions will be determined alongside the total spectral function.
                       By default, no projected DOS type will be calculated (the corresponding projected arrays will be empty).
                       The following options are:

                       * `None` Only total DOS calculated 
                       * `wann` Wannier DOS calculated from the Wannier projectors
        save_to_file : boolean, optional
                       If True, text files with the calculated data will be created.

        Returns
        -------
        Akw         : Dict of numpy arrays
                    (Correlated) k-resolved spectral function.
                    This dictionary has the form of `Akw[spn][n_k, n_om]` where spn, n_k and n_om are the spin, number of k-points, and number of frequencies used in the calculation.
        pAkw        : Dict of numpy arrays
                    (Correlated) k-resolved spectral function projected to atoms (i.e., the Trace of the orbital-projected A(k,w)).
                    This dictionary has the form of pAkw[n_shells][spn][n_k, n_om] where n_shells is the total number of correlated or uncorrelated shells. Empty if `proj_type = None`
        pAkw_orb    : Dict of numpy arrays
                    (Correlated) k-resolved spectral function projected to atoms and
                    resolved into orbital contributions.
                    This dictionary has the form of pAkw[n_shells][spn][n_k, n_om,dim,dim] where dim specifies the orbital dimension of the correlated/uncorrelated shell. Empty if `proj_type = None`
        """

        if (proj_type != None):
            assert proj_type in ('wann'), "'proj_type' must be 'wann' if not None"
        # read in the energy contour energies and projectors
        things_to_read = ['n_k', 'bmat', 'BZ_n_k', 'BZ_iknr', 'BZ_vkl',
                          'n_orbitals', 'proj_mat', 'hopping']
        subgroup_present, values_not_read = self.read_input_from_hdf(
            subgrp=self.cont_data, things_to_read=things_to_read)
        if len(values_not_read) > 0 and mpi.is_master_node:
            raise ValueError(
                'ERROR: One or more necessary SumK input properties have not been found in the given h5 archive:', self.values_not_read)

        if mu is None:
            mu = self.chemical_potential
        if (with_Sigma):
            assert isinstance(
                self.Sigma_imp[0].mesh, MeshReFreq), "SumkDFT.mesh must be real if with_Sigma is True"
            mesh = self.Sigma_imp[0].mesh
        elif mesh is not None:
            assert isinstance(mesh, MeshReFreq), "mesh must be of form MeshReFreq"
            if broadening is None:
                broadening = 0.001
        elif self.mesh is not None:
            assert isinstance(self.mesh, MeshReFreq), "self.mesh must be of form MeshReFreq"
            mesh = self.mesh
            if broadening is None:
                broadening = 0.001
        else:
            assert 0, "ReFreqMesh input required for calculations without real frequency self-energy"
        mesh_val = numpy.linspace(mesh.w_min, mesh.w_max, len(mesh))
        n_om = len(mesh)
        om_minplot = mesh_val[0] - 0.001
        om_maxplot = mesh_val[-1] + 0.001
        # for Fermi Surface calculations
        if FS:
            dw = abs(mesh_val[1]-mesh_val[0])
            # ensure that a few frequencies around the Fermi level are included
            plot_range = [-2*dw, 2*dw]
            mpi.report('Generated A(k,w) will be evaluted at closest frequency to 0.0 in given mesh ')
        if plot_range is None:
            n_om = len(mesh_val[(mesh_val > om_minplot) & (mesh_val < om_maxplot)])
            mesh_val2 = mesh_val[(mesh_val > om_minplot) & (mesh_val < om_maxplot)]
        else:
            om_minplot = plot_range[0]
            om_maxplot = plot_range[1]
            n_om = len(mesh_val[(mesh_val > om_minplot) & (mesh_val < om_maxplot)])
            mesh_val2 = mesh_val[(mesh_val > om_minplot) & (mesh_val < om_maxplot)]
            # \omega ~= 0.0 index for FS file
            abs_mesh_val = [abs(i) for i in mesh_val2]
            jw = [i for i in range(len(abs_mesh_val)) if abs_mesh_val[i]
                  == numpy.min(abs_mesh_val[:])]

        # calculate the spectral functions for the irreducible set of k-points
        [Akw, pAkw, pAkw_orb] = self.gen_Akw(mu=mu, broadening=broadening, mesh=mesh,
                                             plot_shift=0.0, plot_range=plot_range,
                                             shell_list=None, with_Sigma=with_Sigma, with_dc=with_dc,
                                             proj_type=proj_type)

        if save_to_file and mpi.is_master_node():
           spn = self.spin_block_names[self.SO]
           vkc = numpy.zeros(3, float)
           mesh_val2 = mesh_val[(mesh_val > om_minplot) & (mesh_val < om_maxplot)]
           if FS:
             n_om = 1
           else:
             n_om = len(mesh_val2)
           for sp in spn:
               # Open file for storage:
               for iom in range(n_om):
                  if FS:
                    f = open('Akw_FS_' + sp + '.dat', 'w')
                    jom = jw[0]
                  else:
                    f = open('Akw_omega_%s_%s.dat' % (iom, sp), 'w')
                    jom = iom
                  f.write("#Spectral function evaluated at frequency = %s\n" % mesh_val2[jom])
                  for ik in range(self.BZ_n_k):
                     jk = self.BZ_iknr[ik]
                     vkc[:] = numpy.matmul(self.bmat, self.BZ_vkl[ik, :])
                     f.write("%s    %s    %s    %s\n" % (vkc[0], vkc[1], vkc[2], Akw[sp][jk, jom]))
                  f.close()
           if (proj_type != None):
               n_shells = len(pAkw[:])
               for iom in range(n_om):
                  for sp in spn:
                    for ish in range(n_shells):
                      if FS:
                        strng = 'Akw_FS' + '_' + proj_type + '_' + sp + '_proj' + str(ish)
                        jom = jw[0]
                      else:
                        strng = 'Akw_omega_' + str(iom) + '_' + proj_type + \
                            '_' + sp + '_proj' + str(ish)
                        jom = iom
                      f = open(strng + '.dat', 'w')
                      f.write("#Spectral function evaluated at frequency = %s\n" % mesh_val2[jom])
                      for ik in range(self.BZ_n_k):
                        jk = self.BZ_iknr[ik]
                        vkc[:] = numpy.matmul(self.bmat, self.BZ_vkl[ik, :])
                        f.write("%s    %s    %s    %s\n" % (vkc[0], vkc[1], vkc[2],
                                                            pAkw[ish][sp][jk, jom]))
                      f.close()
                      dim = len(pAkw_orb[ish][sp][0, 0, 0, :])
                      for i in range(dim):
                        for j in range(dim):
                          strng2 = strng + '_' + str(i) + '_' + str(j)
                        # Open file for storage:
                          f = open(strng2 + '.dat', 'w')
                          for ik in range(self.BZ_n_k):
                             jk = self.BZ_iknr[ik]
                             vkc[:] = numpy.matmul(self.bmat, self.BZ_vkl[ik, :])
                             f.write("%s    %s    %s    %s\n" % (vkc[0], vkc[1], vkc[2],
                                                                 pAkw_orb[ish][sp][jk, jom, i, j]))
                          f.close()

        return Akw, pAkw, pAkw_orb

    def spaghettis(self, mu=None, broadening=None, mesh=None, plot_shift=0.0, plot_range=None, shell_list=None, with_Sigma=True, with_dc=True, proj_type=None, save_to_file=True):
        """
        Calculates the k-resolved spectral function A(k,w) (band structure)

        The output files have three columns representing the k-point index, frequency and A(k,w) (in this order).

        The output files are as follows:

        - Akw_(sp).dat, the total A(k,w).
        - Akw_(proj_type)_(spn)_proj(i).dat, the A(k,w) projected to shell with index (i).
        - Akw_(proj_type)_(spn)_proj(i)_(m)_(n).dat, as above, but for each (m) and (n) orbital contribution.

        Parameters
        ----------
        mu           : double, optional
                       Chemical potential, overrides the one stored in the hdf5 archive.
                       By default, this is automatically set to the chemical potential within the SK object.
        broadening   : double, optional
                       Lorentzian broadening of the spectra to avoid any numerical artifacts. 
                       If not given, standard value of lattice_gf (0.001 eV) is used.
        mesh         : real frequency MeshType, optional
                       Omega mesh for the real-frequency Green's function.
                       Given as parameter to lattice_gf.
        plot_shift   : double, optional
                       Offset [=(ik-1)*plot_shift, where ik is the index of the k-point] for each A(k,w) for stacked plotting of spectra.
        plot_range   : list of double, optional
                       Sets the energy window for plotting to (plot_range[0],plot_range[1]).
                       If not provided, the min and max values of the energy mesh is used.
        shell_list   : list of integers, optional
                       Contains the indices of the shells of which the projected spectral function
                       is calculated for.
                       If shell_list = None and proj_type is not None, then the projected spectral
                       function is calculated for all shells.
                       Note for experts: The spectra from Wien2k inputs are not rotated to the local coordinate system used in Wien2k.
        with_Sigma   : boolean, optional
                       If True, the self energy is used for the calculation. 
                       If false, the DOS is calculated without self energy.
                       Both with_Sigma and with_dc equal to True is needed for DFT+DMFT A(k,w) calculated. 
                       Both with_Sigma and with_dc equal to false is needed for DFT A(k,w) calculated.
        with_dc      : boolean, optional
                       If True the double counting correction is used.
        proj_type    : string, optional
                        The type of projection used for the orbital-projected DOS.
                        These projected spectral functions will be determined alongside the total spectral function.
                        By default, no projected DOS type will be calculated (the corresponding projected arrays will be empty).
                        The following options are:

                       'None'   - Only total DOS calculated 
                       'wann'   - Wannier DOS calculated from the Wannier projectors
                       'wien2k' - Wien2k orbital-projected DOS from the wien2k theta projectors
        save_to_file : boolean, optional
                       If True, text files with the calculated data will be created.
        
        Returns
        -------
        Akw          : Dict of numpy arrays
                       (Correlated) k-resolved spectral function.
                       This dictionary has the form of `Akw[spn][n_k, n_om]` where spn, n_k and n_om are the spin, number of k-points, and number of frequencies used in the calculation.
        pAkw         : Dict of numpy arrays
                       (Correlated) k-resolved spectral function projected to atoms (i.e., the Trace of the orbital-projected A(k,w)).
                       This dictionary has the form of pAkw[n_shells][spn][n_k, n_om] where n_shells is the total number of correlated or uncorrelated shells.
                       Empty if proj_type = None
        pAkw_orb     : Dict of numpy arrays
                       (Correlated) k-resolved spectral function projected to atoms and
                       resolved into orbital contributions. 
                       This dictionary has the form of pAkw[n_shells][spn][n_k, n_om,dim,dim] where dim specifies the orbital dimension of the correlated/uncorrelated shell.
                       Empty if proj_type = None
        """

        # initialisation
        if (proj_type != None):
            assert proj_type in ('wann', 'wien2k'), "'proj_type' must be either 'wann', 'wien2k'"
            if (proj_type != 'wann'):
                assert proj_type == self.dft_code, "proj_type must be from the corresponding dft inputs."
        things_to_read = ['n_k', 'n_orbitals', 'proj_mat', 'hopping']
        subgroup_present, values_not_read = self.read_input_from_hdf(
            subgrp=self.bands_data, things_to_read=things_to_read)
        if len(values_not_read) > 0 and mpi.is_master_node:
            raise ValueError(
                'ERROR: One or more necessary SumK input properties have not been found in the given h5 archive:', self.values_not_read)
        if (proj_type == 'wien2k'):
           self.load_parproj(data_type='band')

        if mu is None:
            mu = self.chemical_potential
        if (with_Sigma):
            assert isinstance(
                self.Sigma_imp[0].mesh, MeshReFreq), "SumkDFT.mesh must be real if with_Sigma is True"
            mesh = self.Sigma_imp[0].mesh
        elif mesh is not None:
            assert isinstance(mesh, MeshReFreq), "mesh must be of form MeshReFreq"
            if broadening is None:
                broadening = 0.001
        elif self.mesh is not None:
            assert isinstance(self.mesh, MeshReFreq), "self.mesh must be of form MeshReFreq"
            mesh = self.mesh
            if broadening is None:
                broadening = 0.001
        else:
            assert 0, "ReFreqMesh input required for calculations without real frequency self-energy"
        mesh_val = numpy.linspace(mesh.w_min, mesh.w_max, len(mesh))
        n_om = len(mesh)
        om_minplot = mesh_val[0] - 0.001
        om_maxplot = mesh_val[-1] + 0.001
        if plot_range is None:
            om_minplot = mesh_val[0] - 0.001
            om_maxplot = mesh_val[-1] + 0.001
        else:
            om_minplot = plot_range[0]
            om_maxplot = plot_range[1]
        n_om = len(mesh_val[(mesh_val > om_minplot) & (mesh_val < om_maxplot)])

        [Akw, pAkw, pAkw_orb] = self.gen_Akw(mu=mu, broadening=broadening, mesh=mesh,
                                             plot_shift=plot_shift, plot_range=plot_range,
                                             shell_list=shell_list, with_Sigma=with_Sigma, with_dc=with_dc,
                                             proj_type=proj_type)

        if save_to_file and mpi.is_master_node():
            mesh_val2 = mesh_val[(mesh_val > om_minplot) & (mesh_val < om_maxplot)]
            spn = self.spin_block_names[self.SO]
            for sp in spn:
                # Open file for storage:
                f = open('Akw_' + sp + '.dat', 'w')
                for ik in range(self.n_k):
                    for iom in range(n_om):
                        f.write('%s     %s      %s\n' % (ik, mesh_val2[iom], Akw[sp][ik, iom]))
                    f.write('\n')
                f.close()
            if (proj_type != None):
                n_shells = len(pAkw[:])
                if shell_list == None:
                  shell_list = [ish for ish in range(n_shells)]
                for sp in spn:
                  for ish in range(n_shells):
                    jsh = shell_list[ish]
                    f = open('Akw_' + proj_type + '_' +
                             sp + '_proj' + str(jsh) + '.dat', 'w')
                    for ik in range(self.n_k):
                       for iom in range(n_om):
                          f.write('%s     %s      %s\n' % (
                              ik, mesh_val2[iom], pAkw[ish][sp][ik, iom]))
                       f.write('\n')
                    f.close()
                    # get orbital dimension from the length of dimension of the array
                    dim = len(pAkw_orb[ish][sp][0, 0, 0, :])
                    for i in range(dim):
                      for j in range(dim):
                        # Open file for storage:
                        f = open('Akw_' + proj_type + '_' + sp + '_proj' + str(jsh)
                                 + '_' + str(i) + '_' + str(j) + '.dat', 'w')
                        for ik in range(self.n_k):
                            for iom in range(n_om):
                                f.write('%s     %s      %s\n' % (
                                    ik, mesh_val2[iom], pAkw_orb[ish][sp][ik, iom, i, j]))
                            f.write('\n')
                        f.close()

        return Akw, pAkw, pAkw_orb


    def gen_Akw(self, mu, broadening, mesh, plot_shift, plot_range, shell_list, with_Sigma, with_dc, proj_type):
        """
        Internal routine used by spaghettis and spectral_contours to Calculate the k-resolved spectral
        function A(k,w). For advanced users only.

        Parameters
        ----------
        mu           : double
                       Chemical potential, overrides the one stored in the hdf5 archive.
        broadening   : double
                       Lorentzian broadening of the spectra.
        mesh         : real frequency MeshType, optional
                       Omega mesh for the real-frequency Green's function.
                       Given as parameter to lattice_gf.
        plot_shift   : double
                       Offset for each A(k,w) for stacked plotting of spectra.
        plot_range   : list of double
                       Sets the energy window for plotting to (plot_range[0],plot_range[1]).
        shell_list   : list of integers, optional
                       Contains the indices of the shells of which the projected spectral function
                       is calculated for.
                       If shell_list = None and proj_type is not None, then the projected spectral
                       function is calculated for all shells.
        with_Sigma   : boolean
                       If True, the self energy is used for the calculation.
                       If false, the DOS is calculated without self energy.
        with_dc      : boolean
                       If True the double counting correction is used.
        proj_type    : string
                       Output the orbital-projected A(k,w) type from the following:
                       'wann'   - Wannier A(k,w) calculated from the Wannier projectors
                       'wien2k' - Wien2k orbital-projected A(k,w) from the wien2k theta projectors

        Returns
        -------
        Akw          : Dict of numpy arrays
                       (Correlated) k-resolved spectral function
        pAkw      : Dict of numpy arrays
                       (Correlated) k-resolved spectral function projected to atoms.
                       Empty if proj_type = None
        pAkw_orb  : Dict of numpy arrays
                       (Correlated) k-resolved spectral function projected to atoms and
                       resolved into orbital contributions. Empty if proj_type = None
        """

        mesh_val = numpy.linspace(mesh.w_min,mesh.w_max,len(mesh))
        n_om = len(mesh)
        om_minplot = mesh_val[0] - 0.001
        om_maxplot = mesh_val[-1] + 0.001
        if plot_range is None:
            om_minplot = mesh_val[0] - 0.001
            om_maxplot = mesh_val[-1] + 0.001
        else:
            om_minplot = plot_range[0]
            om_maxplot = plot_range[1]
        n_om = len(mesh_val[(mesh_val > om_minplot)&(mesh_val < om_maxplot)])

        #set-up spectral functions
        spn = self.spin_block_names[self.SO]
        Akw = {sp: numpy.zeros([self.n_k, n_om], float) for sp in spn}
        pAkw = []
        pAkw_orb = []
        #set-up projected A(k,w) and parameters if required
        if (proj_type):
            if (proj_type == 'wann'):
                n_shells = self.n_corr_shells
                gf_struct = self.gf_struct_sumk.copy()
                dims = [self.corr_shells[ish]['dim'] for ish in range(n_shells)]
                shells_type = 'corr'
            elif (proj_type == 'wien2k'):
                n_shells = self.n_shells
                gf_struct = [[(sp, self.shells[ish]['dim']) for sp in spn]
                             for ish in range(n_shells)]
                dims = [self.shells[ish]['dim'] for ish in range(n_shells)]
                shells_type = 'all'
            #only outputting user specified parproj shells
            if shell_list!=None:
              for ish in shell_list:
                if(ish > n_shells) or (ish < 0):
                  raise IOError("indices in shell_list input do not correspond \
                                 to existing self.shells indices")
              n_shells = len(shell_list)
              mpi.report("calculating spectral functions for following user specified shell_list:")
              [mpi.report('%s : %s '%(ish, self.shells[ish])) for ish in shell_list]
            else:
              shell_list=[ish for ish in range(n_shells)]
            #projected Akw via projectors
            pAkw = [{} for ish in range(n_shells)]
            pAkw_orb = [{} for ish in range(n_shells)]
            #set-up Green's function object
            G_loc = []
            for ish in range(n_shells):
               jsh=shell_list[ish]
               dim = dims[ish]
               for sp in spn:
                  pAkw[ish][sp] = numpy.zeros([self.n_k, n_om], float)
                  pAkw_orb[ish][sp] = numpy.zeros([self.n_k, n_om, dim, dim], float)
               glist = [GfReFreq(target_shape=(block_dim, block_dim), mesh=mesh)
                   for block, block_dim in gf_struct[ish]]
               G_loc.append(
                   BlockGf(name_list=spn, block_list=glist, make_copies=False))
               G_loc[ish].zero()

        #calculate the spectral function
        ikarray = numpy.array(list(range(self.n_k)))
        for ik in mpi.slice_array(ikarray):
            G_latt_w = self.lattice_gf(ik=ik, mu=mu, broadening=broadening, mesh=mesh, with_Sigma=with_Sigma, with_dc=with_dc)
            # Non-projected A(k,w)
            for bname, gf in G_latt_w:
                Akw[bname][ik] = -gf.data[numpy.where((mesh_val > om_minplot) &
                                    (mesh_val < om_maxplot))].imag.trace(axis1=1, axis2=2)/numpy.pi
                # shift Akw for plotting stacked k-resolved eps(k) curves
                Akw[bname][ik] += ik * plot_shift
            #project spectral functions
            if (proj_type!=None):
                # Projected A(k,w):
                for ish in range(n_shells):
                    G_loc[ish].zero()
                    tmp = G_loc[ish].copy()
                    tmp.zero()
                    tmp << self.proj_type_G_loc(G_latt_w, tmp, ik, ish, proj_type)
                    G_loc[ish] += tmp
                # Rotate to local frame
                if (self.use_rotations):
                  for ish in range(n_shells):
                    jsh=shell_list[ish]
                    for bname, gf in G_loc[ish]:
                        G_loc[ish][bname] << self.rotloc(
                            jsh, gf, direction='toLocal', shells=shells_type)
                for ish in range(n_shells):
                    for bname, gf in G_loc[ish]:  # loop over spins
                        pAkw_orb[ish][bname][ik,:,:,:] = -gf.data[numpy.where((mesh_val > om_minplot) &
                                            (mesh_val < om_maxplot)),:,:].imag/numpy.pi
                        # shift pAkw_orb for plotting stacked k-resolved eps(k) curves
                        pAkw_orb[ish][sp][ik] += ik * plot_shift

        # Collect data from mpi
        mpi.barrier()
        for sp in spn:
          Akw[sp] = mpi.all_reduce(Akw[sp])
          if (proj_type):
            for ish in range(n_shells):
              pAkw_orb[ish][sp] = mpi.all_reduce(pAkw_orb[ish][sp])
              pAkw[ish][sp] = pAkw_orb[ish][sp].trace(axis1=2, axis2=3)
        mpi.barrier()

        return Akw, pAkw, pAkw_orb
        
    def partial_charges(self, mu=None, with_Sigma=True, with_dc=True):
        """
        Calculates the orbitally-resolved density matrix for all the orbitals considered in the input, consistent with
        the definition of Wien2k. Hence, (possibly non-orthonormal) projectors have to be provided in the partial projectors subgroup of
        the hdf5 archive.

        Parameters
        ----------

        with_Sigma : boolean, optional
                     If True, the self energy is used for the calculation. If false, partial charges are calculated without self-energy correction.
        mu : double, optional
             Chemical potential, overrides the one stored in the hdf5 archive.
        with_dc : boolean, optional
                  If True the double counting correction is used.

        Returns
        -------
        dens_mat : list of numpy array
                   A list of density matrices projected to all shells provided in the input.
        """
        assert self.dft_code in ('wien2k'), "This routine has only been implemented for wien2k inputs"

        things_to_read = ['dens_mat_below', 'n_parproj',
                          'proj_mat_all', 'rot_mat_all', 'rot_mat_all_time_inv']
        subgroup_present, values_not_read = self.read_input_from_hdf(
            subgrp=self.parproj_data, things_to_read=things_to_read)
        if len(values_not_read) > 0 and mpi.is_master_node:
            raise ValueError(
                'ERROR: One or more necessary SumK input properties have not been found in the given h5 archive:', self.values_not_read)
        if self.symm_op:
            self.symmpar = Symmetry(self.hdf_file, subgroup=self.symmpar_data)

        spn = self.spin_block_names[self.SO]
        ntoi = self.spin_names_to_ind[self.SO]
        # Density matrix in the window
        self.dens_mat_window = [[numpy.zeros([self.shells[ish]['dim'], self.shells[ish]['dim']], complex)
                                 for ish in range(self.n_shells)]
                                for isp in range(len(spn))]
        # Set up G_loc
        gf_struct_parproj = [[(sp, self.shells[ish]['dim']) for sp in spn]
                             for ish in range(self.n_shells)]
        G_loc = [BlockGf(name_block_generator=[(block, GfImFreq(target_shape=(block_dim, block_dim), mesh=self.mesh))
                                                for block, block_dim in gf_struct_parproj[ish]], make_copies=False)
                    for ish in range(self.n_shells)]
        for ish in range(self.n_shells):
            G_loc[ish].zero()

        ikarray = numpy.array(list(range(self.n_k)))
        for ik in mpi.slice_array(ikarray):

            G_latt_iw = self.lattice_gf(ik=ik, mu=mu, with_Sigma=with_Sigma, with_dc=with_dc)
            G_latt_iw *= self.bz_weights[ik]
            for ish in range(self.n_shells):
                tmp = G_loc[ish].copy()
                for ir in range(self.n_parproj[ish]):
                    for bname, gf in tmp:
                        tmp[bname] << self.downfold(ik, ish, bname, G_latt_iw[
                                                    bname], gf, shells='all', ir=ir)
                    G_loc[ish] += tmp

        # Collect data from mpi:
        for ish in range(self.n_shells):
            G_loc[ish] << mpi.all_reduce(G_loc[ish])
        mpi.barrier()

        # Symmetrize and rotate to local coord. system if needed:
        if self.symm_op != 0:
            G_loc = self.symmpar.symmetrize(G_loc)
        if self.use_rotations:
            for ish in range(self.n_shells):
                for bname, gf in G_loc[ish]:
                    G_loc[ish][bname] << self.rotloc(
                        ish, gf, direction='toLocal', shells='all')

        for ish in range(self.n_shells):
            isp = 0
            for bname, gf in G_loc[ish]:
                self.dens_mat_window[isp][ish] = G_loc[ish].density()[bname]
                isp += 1

        # Add density matrices to get the total:
        dens_mat = [[self.dens_mat_below[ntoi[spn[isp]]][ish] + self.dens_mat_window[isp][ish]
                     for ish in range(self.n_shells)]
                    for isp in range(len(spn))]

        return dens_mat

    def print_hamiltonian(self):
        """
        Prints the Kohn-Sham Hamiltonian to the text files hamup.dat and hamdn.dat (no spin orbit-coupling), or to ham.dat (with spin-orbit coupling).
        """

        if self.SP == 1 and self.SO == 0:
            f1 = open('hamup.dat', 'w')
            f2 = open('hamdn.dat', 'w')
            for ik in range(self.n_k):
                for i in range(self.n_orbitals[ik, 0]):
                    f1.write('%s    %s\n' %
                             (ik, self.hopping[ik, 0, i, i].real))
                for i in range(self.n_orbitals[ik, 1]):
                    f2.write('%s    %s\n' %
                             (ik, self.hopping[ik, 1, i, i].real))
                f1.write('\n')
                f2.write('\n')
            f1.close()
            f2.close()
        else:
            f = open('ham.dat', 'w')
            for ik in range(self.n_k):
                for i in range(self.n_orbitals[ik, 0]):
                    f.write('%s    %s\n' %
                            (ik, self.hopping[ik, 0, i, i].real))
                f.write('\n')
            f.close()


