from __future__ import annotations
from dataclasses import dataclass, field

from FanzineIssueSpecPackage import FanzineDateRange
from HelpersPackage import WikiExtractLink

#------------------------------------
# Just a simple class to conveniently wrap a bunch of data
@dataclass
class ConInstanceInfo:
    #def __init__(self, Link: str="", Text: str="", Loc: str="", DateRange: FanzineDateRange=FanzineDateRange(), Virtual: bool=False, Cancelled: bool=False):
    # NameInSeriesList is the name *displayed* in the table's link
    # If the link is simple, e.g. [[simple link]], then that value should go in NameInSeriesList
    # If the link is complex E.g., [[Link|NameInSeriesList]], the name displayed goes in NameInSeriesList and the page referred to goes in _Link
    # The property Link will always return the actual page referred to
    _Link: str=""
    #TODO: How do we deal with cons with more than one name?
    NameInSeriesList: str=""
    Loc: str=""
    DateRange: FanzineDateRange=field(default=FanzineDateRange())
    Virtual: bool=False
    Cancelled: bool=False
    Override: str=""    # In certain complex cases (a convention with multiple names each of which are linked) we need to override normal name/link handling.

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