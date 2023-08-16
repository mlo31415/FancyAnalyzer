from __future__ import annotations

from typing import Union, List
from collections import defaultdict
from dataclasses import dataclass
import itertools

from FanzineIssueSpecPackage import FanzineDateRange
from Locale import Locale, LocaleHandling

@dataclass
# A class to hold a wiki link of the form [[<link>|<text>]] with the link being optional
# It may have been surrounded by <s></s>
class ConInstanceLink:
    Link: str=""        # The link if different from the display text, else the empty string
    Text: str=""        # The display text. This will always be present
    Cancelled: bool=False

    def __str__(self) -> str:
        return f"{self.Text} {'Link='+self.Link if self.Link != '' else ''}   {'<cancelled>' if self.Cancelled else ''}"


    def __lt__(self, val: ConInstanceLink) -> bool:
        return self.Text < val.Text


#------------------------------------
# Just a simple class to conveniently wrap a bunch of data
class ConInstanceInfo:
    #def __init__(self, Link: str="", Text: str="", Loc: str="", DateRange: FanzineDateRange=FanzineDateRange(), Virtual: bool=False, Cancelled: bool=False):
    # Text is the name *displayed* in the table's link
    # If the link is simple, e.g. [[simple link]], then that value should go in Text.
    # If the link is complex E.g., [[Link|Text]], the name displayed goes in Text and the page referred to goes in _Link
    # The property Link will always return the actual page referred to
    def __init__(self, SeriesName: str | None = None, **kwds):
        kwds=defaultdict(lambda: None, **kwds)    # Turn the dict into a defaultdict with default value None

        self._CIL: List[ConInstanceLink]=[]

        # You can initialize a single Link, Text using the keywords in the constructor
        if kwds["Link"] is not None:
            kwd=kwds["Link"]
            if type(kwd) is str:
                if len(self._CIL) == 0:
                    self._CIL.append(ConInstanceLink())
                self._CIL[0].Link=kwd
            if type(kwd) is list:
                if len(self._CIL) == 0:
                    self._CIL=[ConInstanceLink() for _ in range(len(kwd))]  # Ugly way to initialize to a list of N mutable items
                for i in range(len(kwd)):
                    self._CIL[i].Link=kwd[i]


        if kwds["Text"] is not None:
            kwd=kwds["Text"]
            if type(kwd) is str:
                if len(self._CIL) == 0:
                    self._CIL.append(ConInstanceLink())
                self._CIL[0].Text=kwd
            if type(kwd) is list:
                if len(self._CIL) == 0:
                    self._CIL=[ConInstanceLink() for _ in range(len(kwd))]  # Ugly way to initialize to a list of N mutable items
                for i in range(len(kwd)):
                    self._CIL[i].Text=kwd[i]
        self.SeriesName=SeriesName

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
        s=f"Link={self._CIL[0].Link}  Name={self._CIL[0].Text}  Date={self.DateRange}  Location={self.Locale}"
        if self.Cancelled and not self.DateRange.Cancelled:     # Print this cancelled only if we have not already done so in the date range
            s+="  cancelled=True"
        if self.Virtual:
            s+="  virtual=True"
        return s

    def __eq__(self, other: ConInstanceInfo) -> bool:
        if self.DateRange != other.DateRange or self.Cancelled != other.Cancelled or self.Virtual != other.Virtual:
            return False
        if len(self._CIL) != len(other._CIL):
            return False
        for s, o in zip(self._CIL, other._CIL):
            if s.Text != o.Text:
                return False
            if s.Link != o.Link:
                return False
        return True


    @property
    def Set(self) -> None:
        raise Exception

    # Input: type(text)=str and link left off
    # Input: typw(text)=str and type(link)=str
    # Input: type(text)=list and type(link)=list and len(type) == len(list)
    # Input: type(text)=list and link left off
    @Set.setter
    def Set(self, text: Union[str, List[str]], link:Union[str, List[str]]="") -> None:
        assert (type(text) == str and type(list) == str) or (type(text) == list and type(link) == list and len(text) == len(link)) or (type(text) == list and type(link) == str and link == "")
        if type(text) is str:
            if len(self._CIL) == 0:
                self._CIL.append(ConInstanceLink())
            self._CIL[0].Text=text
            self._CIL[0].Link=link
            return
        if type(text) is list:
            if type(link) == list:
                for t, l in zip(text, link):
                    self._CIL.append(ConInstanceLink(Text=t, Link=l))
            else:
                for t in text:
                    self._CIL.append(ConInstanceLink(Text=t))


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
    def Text(self) -> str:
        if len(self._CIL) == 0:
            return ""
        nl=self._CIL[0].Text
        if len(self._CIL) > 1:
            for i in range(1,len(self._CIL)):
                nl=nl+" / "+self._CIL[i].Text
        return nl
    @Text.setter
    def Text(self, val: Union[str, List[str]]) -> None:
        if type(val) == str:
            val=[val]
        self._NameInSeriesList=val


    @property
    def Link(self) -> str:
        if len(self._CIL) == 0:
            return ""
        if self._CIL[0].Link == "":    # If the link was not set, it's a simple link and just use the displayed text
            return self._CIL[0].Text
        return self._CIL[0].Link
    @Link.setter
    def Link(self, val: Union[str, List[str]]) -> None:
        if type(val) == str:
            val=[val]
        self._Link=val

    # The bare name
    #   Con
    #   Con1 / con 2 / con 3
    @property
    def Name(self) -> str:
        if len(self._CIL) == 0:
            return ""
        out=""
        for i in range(len(self._CIL)):
            if i > 0:
                out+=" / "
            out+=self._CIL[i].Text
        return out

    # The name displayed as a properly linked wiki entry
    # [[link|text]]
    @property
    def LinkedName(self) -> str:
        if len(self._CIL) == 0:
            return ""
        out="[["
        for i in range(len(self._CIL)):
            if i > 0:
                out+="]] / [["
            link=self._CIL[i].Link
            if link != "":
                out+=link+"|"
            out+=self._CIL[i].Text
        out+="]]"
        return out