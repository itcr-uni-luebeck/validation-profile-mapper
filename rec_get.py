"""
Implements function for chained access of dictionaries and lists.
Has additional functionality of throwing exception recursively to document key or index access error during access.
"""


def rec_get(data, *args):
    assert len(args) > 0, "At least one key or index must be supplied"
    try:
        if len(args) == 1:
            return data[args[0]]
        else:
            return rec_get(data[args[0]], *args[1:])
    except (KeyError, IndexError, TypeError) as e:
        raise ParsingKeyError(key=args[0], reason_err=e)
    except ParsingKeyError as pke:
        raise ParsingKeyError(key=args[0], pke=pke)


class ParsingKeyError(Exception):

    def __init__(self, key, reason_err=None, pke=None):
        self.loc = [key]
        if pke is None:
            self.reason = f'{type(reason_err).__name__}: {str(reason_err)}'
        else:
            self.loc.extend(pke.loc)
            self.reason = pke.reason
        self.str_loc = self.generate_str_location(self.loc)
        self.msg = f"Couldn't access using key or index @ {self.str_loc}. Reason: {self.reason}"

    @staticmethod
    def generate_str_location(location):
        msg = list()
        for part in location:
            if type(part) == int:
                msg.append(f'(index) {part}')
            else:
                msg.append(f'(key) {str(part)}')
        return ': '.join(msg)


if __name__ == "__main__":
    d = {'a': ['a0', 'a1', 'a2', 'a3'],
         'b': {'b0': ['b00', 'b01', 'b02'], 'b1': 'text'}}

    print(rec_get(d, 'b', 'b0', 1))

    try:
        rec_get(d, 'a', 4)
    except ParsingKeyError as pke:
        print(pke.msg)

    try:
        rec_get(d, 'b', 'b2')
    except ParsingKeyError as pke:
        print(pke.msg)