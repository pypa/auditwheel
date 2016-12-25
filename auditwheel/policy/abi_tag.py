from ..wheeltools import parse_wheel_info


def valid_wheel_abi_tag(wheel_path: str) -> bool:
    wheel_info = parse_wheel_info(wheel_path)
    if wheel_info['pyver'] in {'cp26', 'cp27', 'cp30', 'cp31', 'cp32'} and wheel_info['abi'] == 'none' and wheel_info['plat'] != 'any':
        return False
    return True

