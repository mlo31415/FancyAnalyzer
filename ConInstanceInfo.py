from __future__ import annotations

from typing import Union, List
from collections import defaultdict
from dataclasses import dataclass

from FanzineIssueSpecPackage import FanzineDateRange
from Locale import Locale, LocaleHandling

@dataclass
# A class to hold a wiki link of the form [[<link>|<text>]] with the link being optional
# It may have been surrounded by <s></s>
class ConInstanceLink:
    Link: str=""        # The link if different from the display text, else the empty string
    Text: str=""        # The display text. This will always be present
    Cancelled: bool=True

    def __str__(self) -> str:
        return f"{self.Text} {'Link='+self.Link if self.Link != '' else ''}   {'<cancelled>' if self.Cancelled else ''}"


    def __lt__(self, val: ConInstanceLink) -> bool:
        return self.Text < val.Text


#------------------------------------
# Just a simple class to conveniently wrap a bunch of data
class ConInstanceInfo:
    #def __init__(self, Link: str="", Text: str="", Loc: str="", DateRange: FanzineDateRange=FanzineDateRange(), Virtual: bool=False, Cancelled: bool=False):
    # NameInSeriesList is the name *displayed* in the table's link
    # If the link is simple, e.g. [[simple link]], then that value should go in NameInSeriesList
    # If the link is complex E.g., [[Link|NameInSeriesList]], the name displayed goes in NameInSeriesList and the page referred to goes in _Link
    # The property Link will always return the actual page referred to
    def __init__(self, **kwds):
        kwds=defaultdict(lambda: None, **kwds)    # Turn the dict into a defaultdict with default value None

        self._Link: List[str]=[]
        if kwds["Link"] is not None:
            self._Link=kwds["Link"]

        self._NameInSeriesList: List[str]=[]
        if kwds["NameInSeriesList"] is not None:
            self._NameInSeriesList=kwds["NameInSeriesList"]

        self._Locale: Locale=Locale()
        if kwds["Locale"] is not None:
            self._Locale=kwds["Locale"]
            if type(self._Locale) is str:
                self._Locale=LocaleHandling().LocaleFromName(self._Locale)  # ()

        self._DateRange: FanzineDateRange=FanzineDateRange()
        if kwds["DateRange"] is not None:
            self._DateRange=kwds["DateRange"]

        self.Virtual: bool=False
        if kwds["Virtual"] is not None:
            self.Virtual=kwds["Virtual"]

        self.Cancelled: bool=False
        if kwds["Cancelled"] is not None:
            self.Cancelled=kwds["Cancelled"]

        # If there's a True cancelled indication in the date range, transfer it to the ConInstanceInfo structure
        if self._DateRange.Cancelled:
            self.Cancelled=True
            self._DateRange.Cancelled=False


    def __str__(self) -> str:
        s=f"Link={self.Link}  Name={self._NameInSeriesList}  Date={self.DateRange}  Location={self.Locale}"
        if self.Cancelled and not self.DateRange.Cancelled:     # Print this cancelled only if we have not already done so in the date range
            s+="  cancelled=True"
        if self.Virtual:
            s+="  virtual=True"
        return s

    def __eq__(self, other: ConInstanceInfo) -> bool:
        return self.NameInSeriesList == other.NameInSeriesList and self.DateRange == other.DateRange and self.Cancelled == other.Cancelled and self.Virtual == other.Virtual


    @property
    def Locale(self) -> Locale:
        if not self._Locale.IsEmpty:
            return self._Locale
        return self._Locale
    @Locale.setter
    def Locale(self, val: Union[str, Locale]):
        if type(val) is str:
            val=LocaleHandling().LocaleFromName(val)  #()
        self._Locale=val

    @property
    def DateRange(self) -> FanzineDateRange:
        return self._DateRange
    @DateRange.setter
    def DateRange(self, val: FanzineDateRange) -> None:
        self._DateRange=val

    @property
    def NameInSeriesList(self) -> str:
        if len(self._NameInSeriesList) == 0:
            return ""
        nl=self._NameInSeriesList[0]
        if len(self._NameInSeriesList) > 1:
            for i in range(1,len(self._NameInSeriesList)):
                nl=nl+" / "+self._NameInSeriesList[i]
        return nl
    @NameInSeriesList.setter
    def NameInSeriesList(self, val: Union[str, List[str]]) -> None:
        if type(val) == str:
            val=[val]
        self._NameInSeriesList=val


    @property
    def Link(self) -> str:
        if self._Link == "":    # If the link was not set, it's a simple link and just use the displayed text
            return self.NameInSeriesList
        return self._Link
    @Link.setter
    def Link(self, val: Union[str, List[str]]) -> None:
        if type(val) == str:
            val=[val]
        self._Link=val

    @property
    def LinkedName(self) -> str:
        if len(self._NameInSeriesList[0]) == 0:
            return ""
        out="[["
        for i in range(len(self._NameInSeriesList)):
            if i > 0:
                out+="]] / [["
            name=self._NameInSeriesList[i]
            link=""
            if i < len(self._Link):
                link=self._Link[i]
            if link != "":
                out+=link+"|"
            out+=name
        out+="]]"
        return out