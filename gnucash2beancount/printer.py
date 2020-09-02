"""
printer.py
================
Print it all!
"""
import sys
from typing import NamedTuple, Union, Optional

from beancount.core import data
from beancount.core.amount import Amount
from beancount.core.data import Account
from beancount.core.data import Flag
from beancount.core.data import Meta
from beancount.core.position import Cost
from beancount.core.position import CostSpec
from beancount.parser import printer

CostBasedPosting = NamedTuple('CostBasedPosting',
                              [('account', Account), ('units', Amount),
                               ('cost', Optional[Union[Cost, CostSpec]]),
                               ('price', Optional[Amount]),
                               ('total_cost', Optional[Amount]),
                               ('flag', Optional[Flag]),
                               ('meta', Optional[Meta])])


class EntryPrinter(printer.EntryPrinter):
    def str(self, entry, oss):
        print(entry, file=oss)

    def CostBasedPosting(self, posting, oss):
        super().Posting(posting, oss)

    # copied from beancount
    def render_posting_strings(self, posting):
        """This renders cost-based posting or normal posting
        """
        if not isinstance(posting, CostBasedPosting):
            return super().render_posting_strings(posting)

        from decimal import Decimal
        from beancount.core import position
        from beancount.core import amount
        from beancount.core import convert

        # Render a string of the flag and the account.
        flag = '{} '.format(posting.flag) if posting.flag else ''
        flag_account = flag + posting.account

        # Render a string with the amount and cost and optional price, if
        # present. Also render a string with the weight.
        weight_str = ''
        if isinstance(posting.units, amount.Amount):
            old_posting = data.Posting(posting.account, posting.units,
                                       posting.cost, posting.price,
                                       posting.flag, posting.meta)
            position_str = position.to_string(old_posting, self.dformat)
            # Note: we render weights at maximum precision, for debugging.
            if posting.cost is None or (isinstance(posting.cost, position.Cost)
                                        and isinstance(posting.cost.number,
                                                       Decimal)):
                weight_str = str(convert.get_weight(old_posting))
        else:
            position_str = ''

        if posting.total_cost is not None:
            position_str += ' @@ {}'.format(
                posting.total_cost.to_string(self.dformat_max))

        return flag_account, position_str, weight_str


# copied from beancount
def print_entries(entries, file=None):
    output = sys.stdout if file is None else file

    previous_type = type(entries[0]) if entries else None
    eprinter = EntryPrinter(render_weight=True)
    for entry in entries:
        # Insert a newline between transactions and
        # between blocks of directives of the same type.
        entry_type = type(entry)
        if (entry_type in (data.Transaction, data.Commodity, str)
                or entry_type is not previous_type):
            output.write('\n')
            if entry_type is str:
                output.write('\n\n')
            previous_type = entry_type

        string = eprinter(entry)
        output.write(string)
