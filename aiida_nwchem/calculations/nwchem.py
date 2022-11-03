# -*- coding: utf-8 -*-
"""Calculation classes for aiida-nwchem."""
import re

from aiida import orm
from aiida.common.datastructures import CalcInfo, CodeInfo
from aiida.engine import CalcJob
import numpy as np

__all__ = ('NwchemBaseCalculation', 'NwchemCalculation')


def validate_parameters(value, ctx=None):  # pylint: disable=unused-argument
    """Validate 'parameters' dict."""
    value.get_dict()


class NwchemBaseCalculation(CalcJob):
    """
    Base calculation class for NWChem.
    """

    # Default input and output files
    _DEFAULT_INPUT_FILE = 'aiida.in'
    _DEFAULT_ABBREVIATION = 'aiida'  # files will be named aiida.db, ...
    _DEFAULT_OUTPUT_FILE = 'aiida.out'
    _DEFAULT_ERROR_FILE = 'aiida.err'

    @classmethod
    def define(cls, spec):
        """Define the process specification."""
        super().define(spec)
        spec.input('input_file', valid_type=orm.SinglefileData, required=True, help='NWChem input file')
        spec.input(
            'restart_folder',
            valid_type=(orm.RemoteData, orm.FolderData),
            required=False,
            help='Remote directory of a completed NWChem calculation to restart from.'
        )

        spec.inputs['metadata']['options']['withmpi'].default = True
        spec.inputs['metadata']['options']['parser_name'].default = 'nwchem.nwchem'
        spec.input('metadata.options.input_filename', valid_type=str, default=cls._DEFAULT_INPUT_FILE)
        spec.input('metadata.options.output_filename', valid_type=str, default=cls._DEFAULT_OUTPUT_FILE)
        spec.input(
            'metadata.options.total_memory',
            valid_type=float,
            default=2000.,
            help='Total memory available per MPI process in MB'
        )

        spec.output('output_parameters', valid_type=orm.Dict)
        spec.output(
            'output_structure', valid_type=orm.StructureData, required=False, help='The relaxed output structure.'
        )

        spec.default_output_node = 'output_parameters'

        # Standard exceptions
        spec.exit_code(
            300, 'ERROR_MISSING_OUTPUT_FILES', message='Required output files are missing.', invalidates_cache=True
        )
        spec.exit_code(
            301,
            'ERROR_NO_RETRIEVED_TEMPORARY_FOLDER',
            message='The retrieved temporary folder could not be accessed.',
            invalidates_cache=True
        )
        spec.exit_code(
            302,
            'ERROR_OUTPUT_STDOUT_MISSING',
            message='The retrieved folder did not contain the required stdout output file.',
            invalidates_cache=True
        )
        spec.exit_code(
            310,
            'ERROR_OUTPUT_STDOUT_READ',
            message='The stdout output file could not be read.',
            invalidates_cache=True
        )
        spec.exit_code(
            312,
            'ERROR_OUTPUT_STDOUT_INCOMPLETE',
            message='The stdout output file was incomplete.',
            invalidates_cache=True
        )
        spec.exit_code(313, 'ERROR_MULTIPLE_CALCULATIONS', message='The stdout contains multiple calculations')
        spec.exit_code(
            340,
            'ERROR_OUT_OF_WALLTIME_INTERRUPTED',
            message='The calculation stopped prematurely because it ran out of walltime but the job was killed by the '
            'scheduler before the files were safely written to disk for a potential restart.',
            invalidates_cache=True
        )
        spec.exit_code(
            350,
            'ERROR_UNEXPECTED_PARSER_EXCEPTION',
            message='The parser raised an unexpected exception.',
            invalidates_cache=True
        )

    def prepare_for_submission(self, folder):
        """Prepare the calculation job for submission by transforming input nodes into input files.
        In addition to the input files being written to the sandbox folder, a `CalcInfo` instance will be returned that
        contains lists of files that need to be copied to the remote machine before job submission, as well as file
        lists that are to be retrieved after job completion.
        :param folder: a sandbox folder to temporarily write files on disk.
        :return: `aiida.common.datastructures.CalcInfo` instance.
        """

        input_filename = folder.get_abs_path(self._DEFAULT_INPUT_FILE)
        with open(input_filename, 'w', encoding='utf-8') as handle:
            handle.write(self._get_input_file())

        _default_commandline_params = [self._DEFAULT_INPUT_FILE]
        codeinfo = CodeInfo()
        codeinfo.cmdline_params = _default_commandline_params
        codeinfo.stdout_name = self._DEFAULT_OUTPUT_FILE
        codeinfo.stderr_name = self._DEFAULT_ERROR_FILE
        codeinfo.code_uuid = self.inputs.code.uuid

        calcinfo = CalcInfo()
        calcinfo.codes_info = [codeinfo]
        calcinfo.stdin_name = self._DEFAULT_INPUT_FILE
        calcinfo.stdout_name = self._DEFAULT_OUTPUT_FILE
        calcinfo.local_copy_list = []
        calcinfo.remote_copy_list = []
        calcinfo.retrieve_list = [self._DEFAULT_OUTPUT_FILE, self._DEFAULT_ERROR_FILE]
        calcinfo.retrieve_singlefile_list = []

        # Symlinks.
        calcinfo.remote_symlink_list = []
        calcinfo.remote_copy_list = []
        if 'restart_folder' in self.inputs:
            comp_uuid = self.inputs.restart_folder.computer.uuid
            remote_path = self.inputs.restart_folder.get_remote_path()
            # Note: this opens a transport but we need to know which files are there
            files = self.inputs.restart_folder.listdir()

            for extension in ('db', 'movecs', 't1amp', 't2amp'):
                # catch files like aiida.db, aiida.t1amp.0001
                rgxp = re.compile(r'.+\.' + extension + r'\.?\d*')
                files_to_link = filter(rgxp.match, files)

                copy_infos = []
                for file_to_link in files_to_link:
                    copy_infos.append((comp_uuid, remote_path + f'/{file_to_link}', file_to_link))

                # If running on the same computer - make a symlink.
                # Except for .db files: Those are typically small, and written/added to
                # by follow-up calculations. Symlinks can therefore lead to confusing results.
                if self.inputs.code.computer.uuid == comp_uuid and extension != 'db':
                    calcinfo.remote_symlink_list += copy_infos
                # If not - copy the folder.
                else:
                    calcinfo.remote_copy_list += copy_infos

        return calcinfo

    def _get_input_file(self) -> str:
        """Prepare NWChem input file from CalcJob inputs.

        This function just returns the content of the 'input_file' input,
        but can be overwritten by child classes to synthesize the
        NWChem input file.
        """
        return self.inputs.input_file.get_content()


class NwchemCalculation(NwchemBaseCalculation):
    """
    Base calculation class for NWChem.

    Synthesizes NWChem input file from parameter dictionary and StructureData.
    """

    @classmethod
    def define(cls, spec):
        """Define the process specification."""
        super().define(spec)
        del spec.inputs['input_file']
        spec.input(
            'parameters', valid_type=orm.Dict, required=True, validator=validate_parameters, help='Input parameters'
        )
        spec.input(
            'structure',
            valid_type=orm.StructureData,
            required=True,
            help='The input structure, with or without a cell'
        )
        spec.input(
            'add_cell',
            valid_type=orm.Bool,
            default=lambda: orm.Bool(False),
            help='The input structure, with or without a cell'
        )
        spec.inputs.validator = cls.validate_inputs

    @staticmethod
    def validate_inputs(value, _):
        """Validate the inputs."""
        if value['add_cell'] and not all(value['structure'].pbc):
            return 'if `add_cell` is `True` then the `structure` needs to have set `pbc` to `(True, True, True)`.'

    def _get_input_file(self):
        """Prepare NWChem input file from CalcJob inputs.

        This overloads the simpler method from the NwchemBaseCalculation class.
        """
        inputs = self.inputs
        parameters = inputs.parameters.get_dict()
        abbreviation = parameters.pop('abbreviation', self._DEFAULT_ABBREVIATION)
        title = parameters.pop('title', 'AiiDA NWChem calculation')
        memory = inputs.metadata.options.total_memory
        basis = parameters.pop('basis', None)
        symmetry = parameters.pop('symmetry', None)
        set_commands = parameters.pop('set', None)
        task = parameters.pop('task', None)
        add_cell = inputs.add_cell

        atom_kinds = []
        atom_coords_cartesian = []
        for site in inputs.structure.sites:
            site_dict = site.get_raw()
            atom_kinds.append(site_dict['kind_name'])
            atom_coords_cartesian.append(site_dict['position'])

        # For calculations with a truly periodic cell, such as solid state calculations,
        # coordinates must be converted into fractional coordinates
        if add_cell:
            cell = inputs.structure.cell
            inv_cell = np.linalg.inv(cell)
            atom_coords_fractional = []
            for coords_cart in atom_coords_cartesian:
                atom_coords_fractional.append(np.dot(coords_cart, inv_cell))

        cell_lengths = inputs.structure.cell_lengths
        cell_angles = inputs.structure.cell_angles

        input_str = ''

        # Echo the input file in the output
        input_str += 'echo\n'
        # Title
        if 'restart_folder' in inputs:
            input_str += f'restart {abbreviation}\ntitle "{title}\"\n'
        else:
            input_str += f'start {abbreviation}\ntitle "{title}\"\n'
        # Memory
        input_str += f'memory {memory} mb\n'
        # Cell
        input_str += 'geometry units angstroms noautoz noautosym\n'
        if add_cell:
            input_str += '  system crystal\n'
            input_str += '    lat_a {}\n    lat_b {}\n    lat_c {}\n'.format(*cell_lengths)  # pylint: disable=consider-using-f-string
            input_str += '    alpha {}\n    beta  {}\n    gamma {}\n'.format(*cell_angles)  # pylint: disable=consider-using-f-string
            input_str += '  end\n'
        if symmetry:
            input_str += f'  symmetry {symmetry}\n'
        # Coordinates
        if add_cell:
            atom_coords = atom_coords_fractional
        else:
            atom_coords = atom_coords_cartesian
        for kind, coords in zip(atom_kinds, atom_coords):
            input_str += '  {} {} {} {}\n'.format(kind, *coords)  # pylint: disable=consider-using-f-string
        input_str += 'end\n'
        # Basis
        if basis:
            input_str += 'basis\n'
            for atom_type, basis_name in basis.items():
                input_str += f'  {atom_type} {basis_name}\n'
            input_str += 'end\n'

        input_str = _convert_parameters(parameters, indent=0, input_str=input_str)

        # Any 'set' commands
        if set_commands:
            for key, value in set_commands.items():
                input_str += f'set {key} {value}\n'

        # Add the task as the final line
        if task:
            input_str += f'task {task}\n'

        return input_str


# Additional free-form parameters
def _convert_parameters(parameters, indent, input_str):
    """Helper function to write out any further parameters passed."""
    for key, value in parameters.items():
        if isinstance(value, dict):
            input_str += ' ' * 4 * indent + f'{key}\n'
            input_str = _convert_parameters(value, indent + 1, input_str=input_str)
            input_str += ' ' * 4 * indent + 'end\n'
        else:
            input_str += ' ' * 4 * indent + f'{key} {value}\n'

    return input_str
