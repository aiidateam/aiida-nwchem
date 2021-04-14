# -*- coding: utf-8 -*-
import os
import shutil

import numpy as np

from aiida import orm
from aiida.engine import CalcJob
from aiida.common.datastructures import CalcInfo, CodeInfo

def validate_parameters(value, ctx=None):  # pylint: disable=unused-argument
    """Validate 'parameters' dict."""
    parameters = value.get_dict()


class NwchemCalculation(CalcJob):
    """
    Base calculation class for NWChem.
    """

    # Default input and output files
    _DEFAULT_INPUT_FILE  = 'aiida.in'
    _DEFAULT_OUTPUT_FILE = 'aiida.out'
    _DEFAULT_ERROR_FILE  = 'aiida.err'
    _DEFAULT_SCRATCH_SUBFOLDER = './scratch'
    _DEFAULT_PERMANENT_SUBFOLDER = './permanent'

    # When restarting, will copy the contents of this folder
    _restart_copy_from = os.path.join(_DEFAULT_PERMANENT_SUBFOLDER, '*')

    # Where to copy files to from a parent_folder
    _restart_copy_to = _DEFAULT_PERMANENT_SUBFOLDER


    @classmethod
    def define(cls, spec):
        """Define the process specification."""
        # yapf: disable
        super().define(spec)
        spec.input('parameters', valid_type=orm.Dict, required=True, validator=validate_parameters,
            help='Input parameters')
        spec.input('structure', valid_type=orm.StructureData, required=True,
            help='The input structure, with or without a cell')
        spec.input('add_cell', valid_type=orm.Bool, default=lambda:orm.Bool(False),
            help='The input structure, with or without a cell')
        spec.input('parent_folder', valid_type=orm.RemoteData, required=False,
            help='An optional working directory of a previously completed calculation to restart from.')
        spec.input('settings', valid_type=orm.Dict, required=False,
            help='Optional parameters to affect the way the calculation job is performed.')

        spec.input('metadata.options.input_filename', valid_type=str, default=cls._DEFAULT_INPUT_FILE)
        spec.input('metadata.options.output_filename', valid_type=str, default=cls._DEFAULT_OUTPUT_FILE)
        spec.input('metadata.options.parser_name', valid_type=str, default='nwchem.nwchem')
        spec.input('metadata.options.withmpi', valid_type=bool, default=True)
        spec.input('metadata.options.total_memory',
            valid_type=float,
            default=2000.,
            help='Total memory available per MPI process in MB')

        spec.output('output_parameters', valid_type=orm.Dict)
        spec.output('output_structure', valid_type=orm.StructureData, required=False,
            help='The relaxed output structure.')

        spec.default_output_node = 'output_parameters'

        # Standard exceptions
        spec.exit_code(201, 'POINT_CHARGE_LIST_INCORRECT',
            message='One of the point charges is not formatted correctly.')
        spec.exit_code(301, 'ERROR_NO_RETRIEVED_TEMPORARY_FOLDER',
            message='The retrieved temporary folder could not be accessed.')
        spec.exit_code(302, 'ERROR_OUTPUT_STDOUT_MISSING',
            message='The retrieved folder did not contain the required stdout output file.')
        spec.exit_code(310, 'ERROR_OUTPUT_STDOUT_READ',
            message='The stdout output file could not be read.')
        spec.exit_code(312, 'ERROR_OUTPUT_STDOUT_INCOMPLETE',
            message='The stdout output file was incomplete.')
        spec.exit_code(313, "ERROR_MULTIPLE_CALCULATIONS",
            message="The stdout contains multiple calculations")    ,
        spec.exit_code(340, 'ERROR_OUT_OF_WALLTIME_INTERRUPTED',
            message='The calculation stopped prematurely because it ran out of walltime but the job was killed by the '
                    'scheduler before the files were safely written to disk for a potential restart.')
        spec.exit_code(350, 'ERROR_UNEXPECTED_PARSER_EXCEPTION',
            message='The parser raised an unexpected exception.')

        # yapf: enable

    def prepare_for_submission(self, folder):
        """Prepare the calculation job for submission by transforming input nodes into input files.
        In addition to the input files being written to the sandbox folder, a `CalcInfo` instance will be returned that
        contains lists of files that need to be copied to the remote machine before job submission, as well as file
        lists that are to be retrieved after job completion.
        :param folder: a sandbox folder to temporarily write files on disk.
        :return: `aiida.common.datastructures.CalcInfo` instance.
        """

        # Initialize settings if set
        if 'settings' in self.inputs:
            settings = self.inputs.settings.get_dict() # Might to make a check for this
        else:
            settings = {}

        parameters = self.inputs.parameters.get_dict()
        restart = parameters.pop('restart',False)
        abbreviation = parameters.pop('abbreviation','aiida_calc')
        title = parameters.pop('title','AiiDA NWChem calculation')
        memory = self.inputs.metadata.options.total_memory
        basis = parameters.pop('basis',None)
        symmetry = parameters.pop('symmetry', None)
        set_commands = parameters.pop('set', None)
        unset_commands = parameters.pop('unset', None)
        task = parameters.pop('task', None)
        add_cell = self.inputs.add_cell
        point_charges = parameters.pop('point_charges', None)

        atom_kinds = []
        atom_coords_cartesian = []
        for site in self.inputs.structure.sites:
            site_dict = site.get_raw()
            atom_kinds.append(site_dict['kind_name'])
            atom_coords_cartesian.append(site_dict['position'])

        # For calculations with a cell, coordinates must be converted to fractional coordinates
        if add_cell:
            cell = self.inputs.structure.cell
            inv_cell = np.linalg.inv(cell)
            atom_coords_fractional = []
            for coords_cart in atom_coords_cartesian:
                atom_coords_fractional.append(np.dot(coords_cart, inv_cell))

        cell_lengths = self.inputs.structure.cell_lengths
        cell_angles = self.inputs.structure.cell_angles

        # Create subfolders for scratch and permanent data
        folder.get_subfolder(self._DEFAULT_SCRATCH_SUBFOLDER, create=True)
        folder.get_subfolder(self._DEFAULT_PERMANENT_SUBFOLDER, create=True)

        input_filename = folder.get_abs_path(self._DEFAULT_INPUT_FILE)
        with open(input_filename,'w') as f:
            # Echo the input file in the output
            f.write('echo\n')
            # Title
            if not restart:
                f.write('start {}\ntitle "{}"\n'.format(abbreviation,title))
            else:
                f.write('restart {}\ntitle "{}"\n'.format(abbreviation,title))
            # Scratch and Permanent folders
            f.write('scratch_dir {}\npermanent_dir {}\n'.format(self._DEFAULT_SCRATCH_SUBFOLDER,
                                                                self._DEFAULT_PERMANENT_SUBFOLDER))
            # Memory
            f.write('memory {} mb\n'.format(memory))
            # Cell
            if not restart:
                f.write('geometry units angstroms noautoz noautosym\n')
                if add_cell:
                    f.write('  system crystal\n')
                    f.write('    lat_a {}\n    lat_b {}\n    lat_c {}\n'.format(*cell_lengths))
                    f.write('    alpha {}\n    beta  {}\n    gamma {}\n'.format(*cell_angles))
                    f.write('  end\n')
                if symmetry:
                    f.write('  symmetry {}\n'.format(symmetry))
                # Coordinates
                if add_cell:
                    atom_coords = atom_coords_fractional
                else:
                    atom_coords = atom_coords_cartesian
                for kind, coords in zip(atom_kinds, atom_coords):
                    f.write('  {} {} {} {}\n'.format(kind, *coords))
                if point_charges:
                    for charge in point_charges:
                        if len(charge) != 4:
                            self.report(f'Point charge list is not correct.')
                            return self.exit_codes.POINT_CHARGE_LIST_INCORRECT
                        else:
                            f.write('  Bq {} {} {} charge {}\n'.format(*charge))
                f.write('end\n')
            # Basis
            if basis:
                f.write('basis\n')
                for atom_type,basis_name in basis.items():
                    f.write('  {} {}\n'.format(atom_type,basis_name))
                f.write('end\n')

            # Unset commands
            if unset_commands:
                for key, value in unset_commands.items():
                    f.write('unset {} {}\n'.format(key,value))

            # Additional free-form parameters
            def convert_parameters(parameters, indent):
                for key, value in parameters.items():
                    if isinstance(value, dict):
                        f.write(' '*4*indent + '{}\n'.format(key))
                        convert_parameters(value, indent+1)
                        f.write(' '*4*indent+'end\n')
                    else:
                        f.write(' '*4*indent + '{} {}\n'.format(key, value))
            convert_parameters(parameters, indent=0)

            # Any 'set' commands
            if set_commands:
                for key, value in set_commands.items():
                    f.write('set {} {}\n'.format(key, value))

            # Add the task as the final line
            if task:
                f.write('task {}\n'.format(task))

            f.flush()

        local_copy_list = []
        remote_copy_list = []
        remote_symlink_list = []

        # Setting a parent folder from previous calculation
        symlink = settings.pop('PARENT_FOLDER_SYMLINK', True)
        if symlink:
            if 'parent_folder' in self.inputs:
                # Put the folder from the previous calculation
                remote_symlink_list.append((
                    self.inputs.parent_folder.computer.uuid,
                    os.path.join(self.inputs.parent_folder.get_remote_path(), 
                                 self._restart_copy_from), self._restart_copy_to
                ))
        else:
            if 'parent_folder' in self.inputs:
                remote_copy_list.append((
                    self.inputs.parent_folder.computer.uuid,
                    os.path.join(self.inputs.parent_folder.get_remote_path(),
                                 self._restart_copy_from), self._restart_copy_to
                ))

        _default_commandline_params = [self._DEFAULT_INPUT_FILE]
        codeinfo =  CodeInfo()
        codeinfo.cmdline_params = _default_commandline_params
        codeinfo.stdout_name = self._DEFAULT_OUTPUT_FILE
        codeinfo.stderr_name = self._DEFAULT_ERROR_FILE
        codeinfo.code_uuid = self.inputs.code.uuid

        calcinfo = CalcInfo()
        calcinfo.codes_info = [codeinfo]
        calcinfo.stdin_name = self._DEFAULT_INPUT_FILE
        calcinfo.stdout_name = self._DEFAULT_OUTPUT_FILE
        calcinfo.local_copy_list = local_copy_list
        calcinfo.remote_copy_list = remote_copy_list
        calcinfo.remote_symlink_list = remote_symlink_list
        calcinfo.retrieve_list = [self._DEFAULT_OUTPUT_FILE,
                                  self._DEFAULT_ERROR_FILE]
        calcinfo.retrieve_singlefile_list = []

        return calcinfo
