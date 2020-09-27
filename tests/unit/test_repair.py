import os
from unittest.mock import patch, call

from auditwheel.patcher import Patchelf
from auditwheel.repair import append_rpath_within_wheel


@patch("auditwheel.patcher._verify_patchelf")
@patch("auditwheel.patcher.check_output")
@patch("auditwheel.patcher.check_call")
class TestRepair:
    def test_append_rpath(self, check_call, check_output, _):
        patcher = Patchelf()
        # When a library has an existing RPATH entry within wheel_dir
        existing_rpath = b"$ORIGIN/.existinglibdir"
        check_output.return_value = existing_rpath
        wheel_dir = '.'
        lib_name = "test.so"
        full_lib_name = os.path.abspath(lib_name)
        append_rpath_within_wheel(lib_name, "$ORIGIN/.lib", wheel_dir, patcher)
        check_output_expected_args = [call(['patchelf', '--print-rpath',
                                            full_lib_name])]
        # Then that entry is preserved when updating the RPATH
        check_call_expected_args = [
            call(['patchelf', '--remove-rpath', full_lib_name]),
            call([
                'patchelf', '--force-rpath', '--set-rpath',
                f'{existing_rpath.decode()}:$ORIGIN/.lib', full_lib_name
            ])
        ]

        assert check_output.call_args_list == check_output_expected_args
        assert check_call.call_args_list == check_call_expected_args

    def test_append_rpath_reject_outside_wheel(self, check_call, check_output, _):
        patcher = Patchelf()
        # When a library has an existing RPATH entry outside wheel_dir
        existing_rpath = b"/outside/wheel/dir"
        check_output.return_value = existing_rpath
        wheel_dir = '/not/outside'
        lib_name = "test.so"
        full_lib_name = os.path.abspath(lib_name)
        append_rpath_within_wheel(lib_name, "$ORIGIN/.lib", wheel_dir, patcher)
        check_output_expected_args = [call(['patchelf', '--print-rpath',
                                            full_lib_name])]
        # Then that entry is eliminated when updating the RPATH
        check_call_expected_args = [call(['patchelf', '--remove-rpath',
                                          full_lib_name]),
                                    call(['patchelf', '--force-rpath',
                                          '--set-rpath',
                                          '$ORIGIN/.lib',
                                          full_lib_name])]

        assert check_output.call_args_list == check_output_expected_args
        assert check_call.call_args_list == check_call_expected_args

    def test_append_rpath_ignore_duplicates(self, check_call, check_output, _):
        patcher = Patchelf()
        # When a library has an existing RPATH entry and we try and append it again
        existing_rpath = b"$ORIGIN"
        check_output.return_value = existing_rpath
        wheel_dir = '.'
        lib_name = "test.so"
        full_lib_name = os.path.abspath(lib_name)
        append_rpath_within_wheel(lib_name, "$ORIGIN", wheel_dir, patcher)
        check_output_expected_args = [call(['patchelf', '--print-rpath',
                                            full_lib_name])]
        # Then that entry is ignored when updating the RPATH
        check_call_expected_args = [call(['patchelf', '--remove-rpath',
                                          full_lib_name]),
                                    call(['patchelf', '--force-rpath',
                                          '--set-rpath',
                                          '$ORIGIN',
                                          full_lib_name])]

        assert check_output.call_args_list == check_output_expected_args
        assert check_call.call_args_list == check_call_expected_args

    def test_append_rpath_ignore_relative(self, check_call, check_output, _):
        patcher = Patchelf()
        # When a library has an existing RPATH entry but it cannot be resolved
        # to an absolute path, it is eliminated
        existing_rpath = b"not/absolute"
        check_output.return_value = existing_rpath
        wheel_dir = '.'
        lib_name = "test.so"
        full_lib_name = os.path.abspath(lib_name)
        append_rpath_within_wheel(lib_name, "$ORIGIN", wheel_dir, patcher)
        check_output_expected_args = [call(['patchelf', '--print-rpath',
                                            full_lib_name])]
        # Then that entry is ignored when updating the RPATH
        check_call_expected_args = [call(['patchelf', '--remove-rpath',
                                          full_lib_name]),
                                    call(['patchelf', '--force-rpath',
                                          '--set-rpath',
                                          '$ORIGIN',
                                          full_lib_name])]

        assert check_output.call_args_list == check_output_expected_args
        assert check_call.call_args_list == check_call_expected_args
