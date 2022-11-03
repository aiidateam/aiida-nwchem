# -*- coding: utf-8 -*-
###########################################################################
# Copyright (c), The AiiDA team. All rights reserved.                     #
# This file is part of the AiiDA code.                                    #
#                                                                         #
# The code is hosted on GitHub at https://github.com/aiidateam/aiida_core #
# For further information on the license, see the LICENSE.txt file        #
# For further information please visit http://www.aiida.net               #
###########################################################################
"""Test module."""
from distutils.version import StrictVersion

try:
    from aiida.orm.data.structure import get_pymatgen_version, has_pymatgen
except ImportError:
    from aiida.orm.nodes.data.structure import get_pymatgen_version, has_pymatgen


def skip_condition():
    return not (has_pymatgen() and StrictVersion(get_pymatgen_version())
                == StrictVersion('4.5.3'))
