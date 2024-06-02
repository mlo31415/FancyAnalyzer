from __future__ import annotations

from typing import Union
from collections import defaultdict
from dataclasses import dataclass

from FanzineIssueSpecPackage import FanzineDateRange
from LocalePage import LocalePage, LocaleHandling
from HelpersPackage import CompressWhitespace

from Log import LogError

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
        self._setOfCIIs: set[str]=set()

    def __getitem__(self, index: str) -> list[ConInstanceInfo]:
        return self._conDict[index]

    def __setitem__(self, index: str, val: ConInstanceInfo):
        self._conDict[index].append(val)
        self._setOfCIIs.add(val.PageName)

    def __contains__(self, item: ConInstanceInfo) -> bool:
        return item in self._conDict.keys()

    def __len__(self) -> int:
        return len(self._conDict)

    def values(self):
        return self._conDict.values()

    # Add entries to the conlist, but filter out duplicate entries
    def Append(self, cii: ConInstanceInfo) -> None:

        if cii.PageName not in self._setOfCIIs:
            # This is a new name: Just append it
            self[cii.PageName]=cii
            return

        if not cii.LocalePage.IsEmpty:
            hits=[y for x in self._conDict.values() for y in x if cii.PageName == y.PageName]
            if hits[0].LocalePage != cii.LocalePage:
                LogError("AppendCon:  existing:  "+str(hits[0]), Print=False)
                LogError("            duplicate - "+str(cii), Print=False)
                # Name exists.  But maybe we have some new information on it?
                # If there are two sources for the convention's location and one is empty, use the other.
                if hits[0].LocalePage.IsEmpty:
                    hits[0].LocalePage=cii.LocalePage
                    LogError("   ...Locale has been updated", Print=False)
        return


###################################################################################
class IndexTableSingleNameEntry:
    def __init__(self, Text: str="", PageName: str= "", Lead: str= "", Remainder: str= "", Cancelled: bool=False, Virtual: bool=False):
        self.Text: str=Text     # The name as given in a convention index table. Link brackets removed.
        self.PageName: str=PageName            # The link to the convention page.  (This is a page name.)
                                # If there is more than one link in the table entry, we ignore links to convention series pages
        self.Lead:str=Lead
        self.Remainder: str=Remainder
        self.Cancelled: bool=Cancelled
        self.Virtual: bool=Virtual
        # A convention's display name comes from the convention series table; a convention's page name is the name of the F3Page`


    def __hash__(self):
        return hash(self.Text)+hash(self.PageName)+hash(self.Lead)+hash(self.Remainder)+hash(self.Cancelled)+hash(self.Virtual)


    def HasLink(self) -> bool:
        return self.PageName != "" or self.Text != ""

    @property
    def BracketContents(self) -> str:
        s=""
        if self.PageName != "":
            s+=self.PageName
        if self.PageName != "" and self.Text != "" and self.PageName != self.Text:
            s+="|"
        if self.Text != "" and self.Text != self.PageName:
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

    def __hash__(self):
        h=0
        if self._listOfEntries is not None:
            for entry in self._listOfEntries:
                h+=entry.__hash__()
        return h

    # This should be the name of the conpage or empty string
    @property
    def PageName(self) -> str:
        numlinks=sum([x.PageName != "" for x in self._listOfEntries])
        if numlinks == 0:
            return ""

        return [x.PageName for x in self._listOfEntries if x.PageName != ""][0]


    @property
    def DisplayNameMarkup(self) -> str:
        # Construct the display name
        displayName=""
        numlinks=sum([x.PageName != "" for x in self._listOfEntries])
        if numlinks > 0:
            # We want to extract the first link, attach it to the first entry, and zero-out all the other links.
            link=[x.PageName for x in self._listOfEntries if x.PageName != ""][0]
            for entry in self._listOfEntries:
                entry.PageName=""
            self._listOfEntries[0].PageName=link

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
            if self._listOfEntries[0].Virtual:
                displayName+=" (virtual)"
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
                if bc != "":
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
                if el.Virtual:
                    displayName+=" (virtual)"
                displayName=CompressWhitespace(displayName)

        return displayName


    @property
    def DisplayNameText(self) -> str:
        # Construct the display name
        displayName=""

        if len(self._listOfEntries) == 1:
            displayName+=self._listOfEntries[0].Lead+" "
            displayName+=self._listOfEntries[0].Text+" "
            displayName+=self._listOfEntries[0].Remainder
        else:
            first=True
            for el in self._listOfEntries:
                if not first:
                    displayName+=" / "
                first=False
                displayName+=el.Lead+" "
                displayName+=el.Text+" "
                displayName+=el.Remainder

        return displayName.strip()




###################################################################################
class IndexTableDateEntry:
    def __init__(self, Dates: list[FanzineDateRange]=None ):
        self._listDatesRanges=Dates

    def __hash__(self):
        h=0
        if self._listDatesRanges is not None:
            for dr in self._listDatesRanges:
                h+=dr.__hash__()
        return h

    def __getitem__(self, item) -> FanzineDateRange:
        return self._listDatesRanges[item]

    def __setitem__(self, key, value):
        self._listDatesRanges[key]=value

    def __len__(self) -> int:
        return len(self._listDatesRanges)

    def __eq__(self, other: IndexTableDateEntry) -> bool:
        if self._listDatesRanges is None and other._listDatesRanges is None:
            return True
        if self._listDatesRanges is None or other._listDatesRanges is None:
            return False

        if len(self._listDatesRanges) != len(other._listDatesRanges):
            return False

        return all([x == y for (x, y) in zip(self._listDatesRanges, other._listDatesRanges)])



###################################################################################
@dataclass
# A class to hold a wiki link of the form [[<link>|<text>]] with the link being optional
# It may have been surrounded by <s></s>
class ConInstanceLink:
    PageName: str=""        # The link if different from the display text, else the empty string
    Text: str=""        # The display text. This will always be present
    Cancelled: bool=False

    def __str__(self) -> str:
        return f"{self.Text} {'Link='+self.PageName if self.PageName != '' else ''}   {'<cancelled>' if self.Cancelled else ''}"


    def __lt__(self, val: ConInstanceLink) -> bool:
        return self.Text < val.Text

    def __hash__(self):
        return self.PageName.__hash__()+self.Text.__hash__()+self.Cancelled.__hash__()


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
    def __init__(self, Names: IndexTableNameEntry=IndexTableNameEntry(), Location: str="", Date: FanzineDateRange=FanzineDateRange(), SeriesName: str= ""):
        self._Names=Names
        self._localePage: LocalePage=LocaleHandling().LocaleFromName(Location)
        self._Date=Date
        self._seriesName=SeriesName


    def __str__(self) -> str:
        s=f"{self._Names.DisplayNameMarkup} {self._Date} {self._localePage})"
        return s

    def __eq__(self, other: ConInstanceInfo) -> bool:
        if self._Names != other._Names:
            return False
        if self._localePage != other._localePage:
            return False
        if self._Date != other._Date:
            return False

        return True


    def __hash__(self):
        return self._Names.__hash__() + self._localePage.__hash__() + self._Date.__hash__() + self._seriesName.__hash__()


    @property
    def LocalePage(self) -> LocalePage:
        if not self._localePage.IsEmpty:
            return self._localePage
        return self._localePage
    @LocalePage.setter
    def LocalePage(self, val: Union[str, LocalePage]):
        if type(val) is str:
            val=LocaleHandling().LocaleFromName(val)  #()
        self._localePage=val


    @property
    def DateRange(self) -> FanzineDateRange:
        return self._Date
    @DateRange.setter
    def DateRange(self, val: FanzineDateRange) -> None:
        self._Date=val


    @property
    def Cancelled(self) -> bool:
        return self._Names[0].Cancelled


    @property
    def Virtual(self) -> bool:
        return self._Names[0].Virtual


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
    def DisplayNameText(self) -> str:
        return self._Names.DisplayNameText
    @DisplayNameText.setter
    def DisplayNameText(self, val: str):
        assert False


    # The name with wiki markup, e.g., "[[Con]]"
    @property
    def DisplayNameMarkup(self) -> str:
        return self._Names.DisplayNameMarkup
    @DisplayNameMarkup.setter
    def DisplayNameMarkup(self, val: str):
        assert False


    # Just the simple name.  For now, it will be the link
    @property
    def PageName(self) -> str:
        return self._Names.PageName


