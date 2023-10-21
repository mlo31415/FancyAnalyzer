from __future__ import annotations

from typing import Union, List

from FanzineIssueSpecPackage import FanzineDateRange
from LocalePage import LocalePage, LocaleHandling

from collections import defaultdict
from dataclasses import dataclass
from Log import Log

###################################################################################
# This class implements a smart list of convention instances with useful information about them stored in a ConInstanceInfo structure
# We do this by reading all the convention series pages' convention tables as well as the individual convention pages
# The dictionary is indexed by
# a convention name
class Conventions:
    def __init__(self):
        # This is a dictionary of all conventions with the convention name as the key.
        self._conDict: defaultdict[str, list[ConInstanceInfo]]=defaultdict(list)
        # Searching for duplicates in the obvious way used to be O(N**2), where N gets to be ~10,000.  Using the set is O(N) and significantly faster.
        self._setOfCIIs: set[ConInstanceInfo]=set()

    def __getitem__(self, index: str) -> list[ConInstanceInfo]:
        return self._conDict[index]

    def __setitem__(self, index: str, val: ConInstanceInfo):
        self._conDict[index].append(val)
        self._setOfCIIs.add(val)

    def __contains__(self, item: ConInstanceInfo) -> bool:
        return item in self._conDict.keys()

    def values(self):
        return self._conDict.values()

    # Add entries to the conlist, but filter out duplicate entries
    def Append(self, ciilist: ConInstanceInfo|list[ConInstanceInfo]) -> None:
        if type(ciilist) is ConInstanceInfo:
            ciilist=[ciilist]

        for cii in ciilist:
            if cii not in self._setOfCIIs:
                # This is a new name: Just append it
                self[cii.DisplayName]=cii
                return

            if not cii.LocalePage.IsEmpty:
                hits=[y for x in self._conDict.values() for y in x if cii == y]
                if hits[0].LocalePage != cii.LocalePage:
                    Log("AppendCon:  existing:  "+str(hits[0]), isError=True, Print=False)
                    Log("            duplicate - "+str(cii), isError=True, Print=False)
                    # Name exists.  But maybe we have some new information on it?
                    # If there are two sources for the convention's location and one is empty, use the other.
                    if hits[0].LocalePage.IsEmpty:
                        hits[0].LocalePage=cii.LocalePage
                        Log("   ...Locale has been updated", isError=True, Print=False)
        return


###################################################################################
@dataclass
class IndexTableSingleNameEntry:
    Text: str=""     # The name as given in a convention index table. Link brackets removed.
    Link: str=""            # The link to the convention page.  (This is a page name.)
                            # If there is more than one link in the table entry, we ignore links to convention series pages
    Lead:str =""
    Remainder: str=""
    Cancelled: bool=False
    Virtual: bool=False
    # A convention's display name comes from the convention series table; a convention's page name is the name of the F3Page

    def HasLink(self) -> bool:
        return self.Link != "" or self.Text != ""

    @property
    def BracketContents(self) -> str:
        s=""
        if self.Link != "":
            s+=self.Link
        if self.Link != "" and self.Text != "" and self.Link != self.Text:
            s+="|"
        if self.Text != "" and self.Text != self.Link:
            s+=self.Text
        return s


###################################################################################
class IndexTableNameEntry:
    def __init__(self):
        self._listOfEntries: list[IndexTableSingleNameEntry]=[]

    def Append(self, itse: IndexTableSingleNameEntry):
            self._listOfEntries.append(itse)

    def __len__(self) -> int:
        return len(self._listOfEntries)

    def __getitem__(self, i: int) -> IndexTableSingleNameEntry:
        return self._listOfEntries[i]

    @property
    def DisplayNameMarkup(self) -> str:
        # Construct the display name
        displayName=""
        numlinks=sum([x.Link != "" for x in self._listOfEntries])
        if numlinks > 0:
            # We want to extract the first link, attach it to the first entry, and zero-out all the other links.
            link=[x.Link for x in self._listOfEntries if x.Link != ""][0]
            for entry in self._listOfEntries:
                entry.Link=""
            self._listOfEntries[0].Link=link

        if len(self._listOfEntries) == 1:
            displayName+=self._listOfEntries[0].Lead
            if self._listOfEntries[0].Cancelled:
                displayName+="<s>"
            bc=self._listOfEntries[0].BracketContents
            if bc != "":
                displayName+="[["+bc+"]]"
            if self._listOfEntries[0].Cancelled:
                displayName+="</s>"
            displayName+=self._listOfEntries[0].Remainder
        else:
            first=True
            for el in self._listOfEntries:
                if not first:
                    displayName+=" / "
                first=False
                bracketsStarted=False
                if el.Cancelled:
                    displayName+="<s>"
                displayName+=el.Lead
                bc=el.BracketContents
                if bc is not "":
                    #displayName+=el.Lead
                    if not bracketsStarted:
                        displayName+="[["
                        bracketsStarted=True
                    displayName+=bc
                    if bracketsStarted:
                        displayName+="]]"
                    bracketsStarted=False
                displayName+=el.Remainder
                if el.Cancelled:
                    displayName+="</s>"

        return displayName


###################################################################################
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

    def __hash__(self):
        return self.Link.__hash__()+self.Text.__hash__()+self.Cancelled.__hash__()


###################################################################################
# Just a simple class to conveniently wrap a bunch of data.
# This represents an F3Page for one instance of a con which happened at a specific time.  If a con waa canceled or moved, then there should be a separate
# ConInstanceInfo for each date. So a con which has been rescheduled is two ConInstanceInfos
# It belongs to one or more consedries.
class ConInstanceInfo:
    #def __init__(self, Link: str="", Text: str="", Loc: str="", DateRange: FanzineDateRange=FanzineDateRange(), Virtual: bool=False, Cancelled: bool=False):
    # Text is the name *displayed* in the table's link
    # If the link is simple, e.g. [[simple link]], then that value should go in Text.
    # If the link is complex E.g., [[Link|Text]], the name displayed goes in Text and the page referred to goes in _Link
    # The property Link will always return the actual page referred to
    def __init__(self, **kwds):
        kwds=defaultdict(lambda: None, **kwds)    # Turn the dict into a defaultdict with default value None

        self._CIL: list[ConInstanceLink]=[]     # This holds a name/link/cancelled for a con.   A ConInstanceInfo might have more than one.
                                                # But when a con is part of two series (e.g., "[[DeepSouthCon 35]] / MidSouthCon 17") but has a single
                                                # F3 page, then the two names is stored in _displayName
        self._seriesName: str=""
        self._displayName: str=""
        self._LocalePage: LocalePage=LocalePage()
        self._DateRange: FanzineDateRange=FanzineDateRange()
        self.Virtual: bool=False
        self.Cancelled: bool=False

        # if kwds["SeriesName"] is None:
        #     return
        # self._seriesName=kwds["SeriesName"]


        # It is required that there be the same number of Links (it can be "") and Texts and that there be at least one
        if type(kwds["Link"]) != type(kwds["Text"]):
            i=0

        # You can initialize a single Link, Text using the keywords in the constructor
        kwd=kwds["Link"]
        if type(kwd) is str:
            self._CIL.append(ConInstanceLink())
            self._CIL[0].Link=kwd
        if type(kwd) is list:
            self._CIL=[ConInstanceLink() for _ in range(len(kwd))]  # Ugly way to initialize to a list of N mutable items
            for i in range(len(kwd)):
                self._CIL[i].Link=kwd[i]

        kwd=kwds["Text"]
        if type(kwd) is str:
            self._CIL[0].Text=kwd
        if type(kwd) is list:
            for i in range(len(kwd)):
                self._CIL[i].Text=kwd[i]

        if kwds["Locale"] is not None:
            self._LocalePage=kwds["Locale"]
            if type(self._LocalePage) is str:
                self._LocalePage=LocaleHandling().LocaleFromName(self._LocalePage)  # ()


        if kwds["DsiplayName"] is not None:
            self._displayName=kwds["DisplayName"]

        if kwds["DateRange"] is not None:
            self._DateRange=kwds["DateRange"]

        if kwds["Virtual"] is not None:
            self.Virtual=kwds["Virtual"]

        if kwds["Cancelled"] is not None:
            self.Cancelled=kwds["Cancelled"]

        # If there's a True cancelled indication in the date range, transfer it to the ConInstanceInfo structure
        if self._DateRange.Cancelled:
            self.Cancelled=True
            self._DateRange.Cancelled=False


    def __str__(self) -> str:
        if len(self._CIL) > 0:
            s=f"Link={self._CIL[0].Link}  Name={self._CIL[0].Text}  Date={self.DateRange}  Location={self.LocalePage}"
        else:
            s=f"Link=None  Name=None  Date={self.DateRange}  Location={self.LocalePage}"

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

    def __hash__(self):
        h=self.Cancelled.__hash__()
        if self.Link is not None:
            h+=self.Link.__hash__()
        if self.DateRange is not None:
            h+=self.DateRange.__hash__()
        if self._CIL is not None:
            h+=sum([x.__hash__() for x in self._CIL if x is not None])
        return h


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
    def LocalePage(self) -> LocalePage:
        if not self._LocalePage.IsEmpty:
            return self._LocalePage
        return self._LocalePage
    @LocalePage.setter
    def LocalePage(self, val: Union[str, LocalePage]):
        if type(val) is str:
            val=LocaleHandling().LocaleFromName(val)  #()
        self._LocalePage=val

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
        assert False    # Should never do a set


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
        assert False    # Should never do a set


    # The name of the series this con is a member of
    @property
    def SeriesName(self) -> str:
        return self._seriesName
    @SeriesName.setter
    def SeriesName(self, val: str):
        self._seriesName=val


    # The bare name
    #   Con
    #   Con1 / con 2 / con 3
    @property
    def DisplayName(self) -> str:
        # if len(self._CIL) == 0:
        #     return ""
        # out=""
        # for i in range(len(self._CIL)):
        #     if i > 0:
        #         out+=" / "
        #     out+=self._CIL[i].Text
        # return out
        return self._displayName
    @DisplayName.setter
    def DisplayName(self, val: str):
        self._displayName=val


    # The name displayed as a properly linked wiki entry
    # [[link|text]]
    @property
    def LinkedName(self) -> str:
        if len(self._CIL) == 0:
            return ""
        # If there is more than one linked name, create a single name using "/" between the names
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
