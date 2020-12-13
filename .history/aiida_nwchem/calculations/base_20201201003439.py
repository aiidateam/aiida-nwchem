# -*- coding: utf-8 -*-
import os
import shutil

from aiida.orm.calculation.job import JobCalculation
from aiida.orm.data.parameter import ParameterData
from aiida.orm.data.structure import StructureData
from aiida.common.datastructures import CalcInfo, CodeInfo
from aiida.common.exceptions import InputValidationError
from aiida.common.utils import classproperty


class NwchemCalculationBase(JobCalculation):
    """
    Base calcultion class for NWChem.
    """


    @classmethod
    def define(cls, spec):
        super(NwchemCalculationBase, cls).define(spec)
        spec.input('restart_folder', valid_type=get_data_class('remote'), help='A remote folder to restart from if need be', required=False)


    def _init_internal_params(self):
        super(BasicCalculation, self)._init_internal_params()

        # Name of the default parser
        self._default_parser = 'nwchem.base'

        # Default input and output files
        self._DEFAULT_INPUT_FILE  = 'aiida.in'
        self._DEFAULT_OUTPUT_FILE = 'aiida.out'
        self._DEFAULT_ERROR_FILE  = 'aiida.err'

        # Default command line parameters
        self._default_commandline_params = [ self._DEFAULT_INPUT_FILE ]

    @classproperty
    def _use_methods(cls):
        retdict = JobCalculation._use_methods
        retdict.update({
            "structure": {
               'valid_types': StructureData,
               'additional_parameter': None,
               'linkname': 'structure',
               'docstring': "A structure to be processed",
               },
            "parameters": {
               'valid_types': ParameterData,
               'additional_parameter': None,
               'linkname': 'parameters',
               'docstring': "Parameters used to describe the calculation",
               },
            })
        return retdict

    def _prepare_for_submission(self,tempfolder,inputdict):
        import numpy as np

        try:
            struct = inputdict.pop(self.get_linkname('structure'))
        except KeyError:
            raise InputValidationError("no structure is specified for this calculation")
        if not isinstance(struct, StructureData):
            raise InputValidationError("struct is not of type StructureData")

        try:
            code = inputdict.pop(self.get_linkname('code'))
        except KeyError:
            raise InputValidationError("no code is specified for this calculation")

        atoms = struct.get_ase()

        lat_lengths = [
            (atoms.cell[0]**2).sum()**0.5,
            (atoms.cell[1]**2).sum()**0.5,
            (atoms.cell[2]**2).sum()**0.5,
        ]

        lat_angles = np.arccos([
            np.vdot(atoms.cell[1],atoms.cell[2])/lat_lengths[1]/lat_lengths[2],
            np.vdot(atoms.cell[0],atoms.cell[2])/lat_lengths[0]/lat_lengths[2],
            np.vdot(atoms.cell[0],atoms.cell[1])/lat_lengths[0]/lat_lengths[1],
        ])/np.pi*180

        parameters = inputdict.pop(self.get_linkname('parameters'), None)
        if parameters is None:
            parameters = ParameterData(dict={})
        if not isinstance(parameters, ParameterData):
            raise InputValidationError("parameters is not of type ParameterData")
        par = parameters.get_dict()

        abbreviation = par.pop('abbreviation','aiida_calc')
        title = par.pop('title','AiiDA NWChem calculation')
        basis = par.pop('basis',None)
        task = par.pop('task','scf')
        add_cell = par.pop('add_cell',True)

        if basis is None:
            basis = dict()
            for atom_type in set(atoms.get_chemical_symbols()):
                basis[atom_type] = 'library 6-31g'

        input_filename = tempfolder.get_abs_path(self._DEFAULT_INPUT_FILE)
        with open(input_filename,'w') as f:
            # Title
            f.write('start {}\ntitle "{}"\n\n'.format(abbreviation,title))
            # Cell 
            f.write('geometry units au\n')
            if add_cell:
                f.write('  system crystal\n')
                f.write('    lat_a {}\n    lat_b {}\n    lat_c {}\n'.format(*lat_lengths))
                f.write('    alpha {}\n    beta  {}\n    gamma {}\n'.format(*lat_angles))
                f.write('  end\n')
            # Coordinates
            for i,atom_type in enumerate(atoms.get_chemical_symbols()):
                f.write('    {} {} {} {}\n'.format(atom_type,
                                               atoms.get_positions()[i][0],
                                               atoms.get_positions()[i][1],
                                               atoms.get_positions()[i][2]))
            # Basis
            f.write('end\nbasis\n')
            for atom_type,b in basis.iteritems():
                f.write('    {} {}\n'.format(atom_type,b))
            # Additional free-form parameters
            for param, value in par.items():
                if type(value) is dict:
                    f.write('{}\n'.format(param))
                    for subparam, subvalue in value.items():
                        f.write('  {}    {}\n'.format(subparam, subvalue)) 
                    f.write('end\n')
                else:
                    f.write('{}    {}\n'.format(param, value)) 
            # Task (only one permitted - see full.py for complex calculations)
            f.write('end\ntask {}\n'.format(task))
            f.flush()

        commandline_params = self._default_commandline_params

        calcinfo = CalcInfo()
        calcinfo.uuid = self.uuid
        calcinfo.local_copy_list = []
        calcinfo.remote_copy_list = []
        calcinfo.retrieve_list = [self._DEFAULT_OUTPUT_FILE,
                                  self._DEFAULT_ERROR_FILE]
        calcinfo.retrieve_singlefile_list = []

        codeinfo = CodeInfo()
        codeinfo.cmdline_params = commandline_params
        codeinfo.stdout_name = self._DEFAULT_OUTPUT_FILE
        codeinfo.stderr_name = self._DEFAULT_ERROR_FILE
        codeinfo.code_uuid = code.uuid
        calcinfo.codes_info = [codeinfo]

        return calcinfo
