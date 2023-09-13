"""This file contains nxdrive.log filter patterns to mask the sensitive information.
To add more filters, add it in the form of tuple(). For example: (r"regex_to_filter_data", r"mask_string")
"""

patterns = [
    (
        r"token\/([0-9a-f]{8}-[0-9a-f]{4}-[0-5][0-9a-f]{3}-[089ab][0-9a-f]{3}-[0-9a-f]{12})",
        r"token/*********",
    ),
    (
        r"token\W:\s\W([0-9a-f]{8}-[0-9a-f]{4}-[0-5][0-9a-f]{3}-[089ab][0-9a-f]{3}-[0-9a-f]{12})",
        r"token': '*********",
    ),
    (r"extraInfo': {(.*?)}", r"extraInfo': {}"),
    (r"X-Amz-Security-Token=(.*?)&", r"X-Amz-Security-Token=*********&"),
    (
        r"X-Amz-Credential=(.*?)}",
        r"X-Amz-Credential=*********&X-Amz-Signature=*********",
    ),
]
