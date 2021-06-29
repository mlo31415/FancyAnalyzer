from __future__ import annotations
from dataclasses import dataclass, field

from FanzineIssueSpecPackage import FanzineDateRange
from HelpersPackage import WikiExtractLink

#------------------------------------
# Just a simple class to conveniently wrap a bunch of data
@dataclass
class ConInfo:
    #def __init__(self, Link: str="", Text: str="", Loc: str="", DateRange: FanzineDateRange=FanzineDateRange(), Virtual: bool=False, Cancelled: bool=False):
    # The link is the name of the page referred to
    # NameInSeriesList is the name displayed in the table   E.g., [[Link|NameInSeriesList]]
    # If the link is simple, e.g. [[simple link]], then that value should go in NameInSeriesList
    _Link: str=""
    NameInSeriesList: str=""
    Loc: str=""
    DateRange: FanzineDateRange=field(default=FanzineDateRange())
    Virtual: bool=False
    Cancelled: bool=False
    Override: str=""

    def __str__(self) -> str:
        s="Link="+self.Link+"  Name="+self.NameInSeriesList+"  Date="+str(self.DateRange)+"  Location="+self.Loc
        if self.Cancelled and not self.DateRange.Cancelled:     # Print this cancelled only if we have not already done so in the date range
            s+="  cancelled=True"
        if self.Virtual:
            s+=" virtual=True"
        if len(self.Override) > 0:
            s+="  Override="+self.Override
        return s

    def SetLoc(self, val: str):
        # We don't want any links in this
        self.Loc=WikiExtractLink(val)

    @property
    def Link(self) -> str:
        if self._Link == "":    # If the link was not set, it's a simple link and just use the displayed text
            return self.NameInSeriesList
        return self._Link
    @Link.setter
    def Link(self, val: str) -> None:
        self._Link=val