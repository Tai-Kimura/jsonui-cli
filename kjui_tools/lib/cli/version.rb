# frozen_string_literal: true

module KjuiTools
  module CLI
    # Toolchain version. Single source of truth is the jsonui-cli root VERSION
    # file; this constant is a standalone copy for consumer-project installs
    # (where the root file is absent) and is locked to the root VERSION by
    # jui_tools/tests/test_version_lockstep.py.
    VERSION = '1.8.24'
  end
end
