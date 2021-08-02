from __future__ import annotations

from typing import Dict, List, Tuple, Optional, Union
from dataclasses import dataclass

import os
import re
from datetime import datetime

from Locale import LocaleHandling, Locale
from F3Page import F3Page, DigestPage, TagSet
from Log import Log, LogOpen, LogSetHeader
from HelpersPackage import WindowsFilenameToWikiPagename, WikiExtractLink, CrosscheckListElement, ScanForBracketedText,WikidotCanonicizeName
from ConInstanceInfo import ConInstanceInfo
from FanzineIssueSpecPackage import FanzineDateRange


def main():
    # We'll work entirely on the local copies of the two sites.

    # For Fancy 3 on MediaWiki, there are many names to keep track of for each page:
    #       The actual, real-world name.  But this can't always be used for a filename on Windows or a page name in Mediawiki, so:
    #       WikiPagename -- the name of the MediaWiki page it was created with and as it appears in a simple Mediawiki link.
    #       URLname -- the name of the Mediawiki page in a URL
    #                       Basically, spaces are replaced by underscores and the first character is always UC.  #TODO: What about colons? Other special characters?
    #       WindowsFilename -- the name of the Windows file in the in the local site: converted using methods in HelperPackage. These names can be derived from the Mediawiki page name and vice-versa.
    #       WikiDisplayname -- the display name in MediaWiki: Normally the name of the page, but can be overridden on the page using DISPLAYTITLE
    #
    #       The URLname and WindowsFilename can be derived from the WikiPagename, but not necessarily vice-versa

    # The local version of the site is a pair (sometimes also a folder) of files with the Wikidot name of the page.
    # <name>.txt is the text of the current version of the page
    # <name>.xml is xml containing meta date. The metadata we need is the tags
    # If there are attachments, they're in a folder named <name>. We don't need to look at that in this program
    fancySitePath=r"C:\Users\mlo\Documents\usr\Fancyclopedia\Python\site"   # Location of a local copy of the site maintained by FancyDownloader
    LogOpen("Log.txt", "Error Log.txt")

    # Create a list of the pages on the site by looking for .txt files and dropping the extension
    Log("***Querying the local copy of Fancy 3 to create a list of all Fancyclopedia pages")
    Log("   path='"+fancySitePath+"'")
    allFancy3PagesFnames = [f[:-4] for f in os.listdir(fancySitePath) if os.path.isfile(os.path.join(fancySitePath, f)) and f[-4:] == ".txt"]
    allFancy3PagesFnames = [f for f in allFancy3PagesFnames if not f.startswith("index_")]     # Drop index pages
    allFancy3PagesFnames = [f for f in allFancy3PagesFnames if not f.endswith(".js")]     # Drop javascript page
    # The following lines are for debugging and are used to select a subset of the pages for greater speed
    #allFancy3PagesFnames= [f for f in allFancy3PagesFnames if f[0] in "A"]        # Just to cut down the number of pages for debugging purposes
    #allFancy3PagesFnames= [f for f in allFancy3PagesFnames if f[0:6].lower() == "windyc" or f[0:5].lower() == "new z"]        # Just to cut down the number of pages for debugging purposes
    #allFancy3PagesFnames= [f for f in allFancy3PagesFnames if f[0:7].lower() == "boskone"]        # Just to cut down the number of pages for debugging purposes

    # We ignore pages with certain prefixes
    excludedPrefixes=["_admin", "Template;colon", "User;colon", "Log 2"]
    for prefix in excludedPrefixes:
        allFancy3PagesFnames = [f for f in allFancy3PagesFnames if not f.startswith(prefix)]

    # And we exclude certain specific pages
    excludedPages=["Admin", "Standards", "Test Templates"]
    allFancy3PagesFnames=[f for f in allFancy3PagesFnames if f not in excludedPages]
    Log("   "+str(len(allFancy3PagesFnames))+" pages found")

    # The master dictionary of all Fancy 3 pages.
    fancyPagesDictByWikiname: Dict[str, F3Page]={}     # Key is page's name on the wiki; Value is a F3Page class containing all the references, tags, etc. on the page

    Log("***Scanning local copies of pages for links and other info")
    for pageFname in allFancy3PagesFnames:
        val=DigestPage(fancySitePath, pageFname)
        if val is not None:
            fancyPagesDictByWikiname[val.Name]=val
        # This is a very slow process, so print progress indication on the console
        l=len(fancyPagesDictByWikiname)
        if l%1000 == 0:     # Print only when divisible by 1000
            if l>1000:
                Log("--", noNewLine=l%20000 != 0)  # Add a newline only when divisible by 20,000
            Log(str(l), noNewLine=True)
    Log(f"   {len(fancyPagesDictByWikiname)} semi-unique links found")


    Log(f"{datetime.now():%H:%M:%S}: Writing: Redirects to Wikidot pages.txt")
    with open("Redirects to Wikidot pages.txt", "w+", encoding='utf-8') as f:
        for key, val in fancyPagesDictByWikiname.items():
            for link in val.OutgoingReferences:
                if link.LinkWikiName in fancyPagesDictByWikiname.keys():
                    if fancyPagesDictByWikiname[link.LinkWikiName].IsWikidotRedirectPage:
                        print(f"Page '{key}' has a pointer to Wikidot redirect page '{link.LinkWikiName}'", file=f)


    # Build a locale database
    Log("\n\n***Building a locale dictionary")
    LocaleHandling().Create(fancyPagesDictByWikiname)

    Log("***Analyzing convention series tables")

    # Scan for a virtual flag
    # Return True/False and remaining text after V-flag is removed
    def ScanForVirtual(s: str) -> Tuple[bool, str]:
        pattern = "\((:?virtual|online|held online|moved online|virtual convention)\)"

        # First look for the alternative contained in parens *anywhere* in the text
        newval = re.sub(pattern, "", s, flags=re.IGNORECASE)  # Check w/parens 1st so that if parens exist, they get removed.
        if s != newval:
            return True, newval.strip()

        # Now look for alternatives by themselves.  So we don't pick up junk, we require that the non-parenthesized alternatives be alone in the cell
        newval = re.sub("\s*" + pattern + "\s*$", "", s, flags=re.IGNORECASE)
        if s != newval:
            return True, newval.strip()

        return False, s


    # Create a list of convention instances with useful information about them stored in a ConInstanceInfo structure
    # We do this be reading all the convention series pages' convention tables
    conventions: Dict[str, ConInstanceInfo]={}
    for page in fancyPagesDictByWikiname.values():

        # First, see if this is a Conseries page
        if not page.IsConSeries:
            continue

        LogSetHeader("Processing "+page.Name)

        # Sometimes there will be multiple tables, so we check each of them
        for index, table in enumerate(page.Tables):
            numcolumns=len(table.Headers)

            listConLocationHeaders=["Location"]
            locColumn=CrosscheckListElement(listConLocationHeaders, table.Headers)
            # We don't log a missing location column because that is common and not an error -- we'll try to get the location later from the con instance's page

            listConNameHeaders=["Convention", "Convention Name", "Name"]
            conColumn=CrosscheckListElement(listConNameHeaders, table.Headers)
            if conColumn is None:
                Log("***Can't find Convention column in table "+str(index+1)+" of "+str(len(page.Tables)), isError=True)
                continue

            listConDateHeaders=["Date", "Dates"]
            dateColumn=CrosscheckListElement(listConDateHeaders, table.Headers)
            if dateColumn is None:
                Log("***Can't find Dates column in table "+str(index+1)+" of "+str(len(page.Tables)), isError=True)
                continue

            # Make sure the table has rows
            if table.Rows is None:
                Log(f"***Table {index+1} of {len(page.Tables)} looks like a convention table, but has no rows", isError=True)
                continue

            # We have a convention table.  Walk it, extracting the individual conventions
            for row in table.Rows:
                LogSetHeader(f"Processing: {page.Name}  row: {row}")
                # Skip rows with merged columns, and also rows where either the date cell or the convention name cell is empty
                if len(row) < numcolumns or len(row[conColumn]) == 0  or len(row[dateColumn]) == 0:
                    continue

                # Check the row for (virtual) in any form. If found, set the virtual flag and remove the text from the line
                virtual=False
                for idx, col in enumerate(row):
                    v2, col=ScanForVirtual(col)
                    if v2:
                        row[idx]=col      # Update row with the virtual flag removed
                    virtual=virtual or v2
                Log("Virtual="+str(virtual), Print=False)

                # Decode the convention and date columns add the resulting convention(s) to the list
                # This is really complicated since there are (too) many cases and many flavors to the cases.  The cases:
                #   name1 || date1          (1 con: normal)
                #   <s>name1</s> || <s>date1</s>        (1: cancelled)
                #   <s>name1</s> || date1        (1: cancelled)
                #   name1 || <s>date1</s>        (1: cancelled)
                #   <s>name1</s> name2 || <s>date1</s> date2        (2: cancelled and then re-scheduled)
                #   name1 || <s>date1</s> date2             (2: cancelled and rescheduled)
                #   <s>name1</s> || <s>date1</s> date2            (2: cancelled and rescheduled)
                #   <s>name1</s> || <s>date1</s> <s>date2</s>            (2: cancelled and rescheduled and cancelled)
                #   <s>name1</s> name2 || <s>date1</s> date2            (2: cancelled and rescheduled under new name)
                #   <s>name1</s> <s>name2</s> || <s>date1</s> <s>date2</s>            (2: cancelled and rescheduled under new name and then cancelled)
                # and all of these cases may have the virtual flag, but it is never applied to a cancelled con unless that is the only option
                # Basically, the pattern is 1 || 1, 1 || 2, 2 || 1, or 2 || 2 (where # is the number of items)
                # 1:1 and 2:2 match are yield two cons
                # 1:2 yields two cons if 1 date is <s>ed
                # 2:1 yields two cons if 1 con is <s>ed
                # The strategy is to sort out each column separately and then try to merge them into conventions
                # Note that we are disallowing the extreme case of three cons in one row!

                # First the dates
                datetext = row[dateColumn]

                # For the dates column, we want to remove the virtual designation as it will just confuse later processing.
                # We want to handle the case where (virtual) is in parens, but also when it isn't.
                # We need two patterns here because Python's regex doesn't have balancing groups and we don't want to match unbalanced parens

                # Ignore anything in trailing parenthesis. (e.g, "(Easter weekend)", "(Memorial Day)")
                datetext=re.sub("\(.*\)\s?$", "", datetext)   # Note that this is greedy. Is that the correct things to do?
                # Convert the HTML characters some people have inserted into their ascii equivalents
                datetext=datetext.replace("&nbsp;", " ").replace("&#8209;", "-")
                # Remove leading and trailing spaces
                datetext=datetext.strip()

                # Now look for dates. There are many cases to consider:
                #1: date                    A simple date (note that there will never be two simple dates in a dates cell)
                #2: <s>date</s>             A canceled con's date
                #3: <s>date</s> date        A rescheduled con's date
                #4: <s>date</s> <s>date</s> A rescheduled and then cancelled con's dates
                #5: <s>date</s> <s>date</s> date    A twice-rescheduled con's dates
                #m=re.match("^(:?(<s>.+?</s>)\s*)*(.*)$", datetext)
                pat="<s>.+?</s>"
                ds=re.findall(pat, datetext)
                if len(ds) > 0:
                    datetext=re.sub(pat, "", datetext).strip()
                if len(datetext)> 0:
                    ds.append(datetext)
                if len(ds) == 0:
                    Log("Date error: "+datetext)
                    continue

                # We have N groups up to N-1 of which might be None
                dates:List[FanzineDateRange]=[]
                for d in ds:
                    if len(d) > 0:
                        c, s=ScanForBracketedText(d, "s")
                        dr=FanzineDateRange().Match(s)
                        dr.Cancelled=c
                        if dr.Duration() > 7:
                            Log("??? convention has long duration: "+str(dr), isError=True)
                        if not dr.IsEmpty():
                            dates.append(dr)

                if len(dates) == 0:
                    Log(f"***No dates found - {page.Name}  row: {row}", isError=True)
                elif len(dates) == 1:
                    Log(f"{page.Name}  row: {row}: 1 date: {dates[0]}", Print=False)
                else:
                    Log(f"{page.Name}  row: {row}: {len(dates)} dates: {dates[0]}", Print=False)
                    for d in dates[1:]:
                        Log(f"           {d}", Print=False)


                # Get the corresponding convention name(s).
                context=row[conColumn]
                # Clean up the text
                # Convert the HTML characters some people have inserted into their ascii equivalents
                context=context.replace("&nbsp;", " ").replace("&#8209;", "-")
                # And get rid of hard line breaks
                context=context.replace("<br>", " ")
                # In some pages we italicize or bold the con's name, so remove spans of single quotes 2 or longer
                context=re.sub("[']{2,}", "", context)

                context=context.strip()

                if context.count("[[") != context.count("]]"):
                    Log("'"+row[conColumn]+"' has unbalanced double brackets. This is unlikely to end well...", isError=True)

                # An individual name is of one of these forms:
                    #   xxx
                    # [[xxx]] zzz               Ignore the "zzz"
                    # [[xxx|yyy]]               Use just xxx
                    # [[xxx|yyy]] zzz
                # But! There can be more than one name on a date if a con converted from real to virtual while changing its name and keeping its dates:
                # E.g., <s>[[FilKONtario 30]]</s> [[FilKONtari-NO]] (trailing stuff)
                # Whatcon 20: This Year's Theme -- need to split on the colon
                # Each of the bracketed chunks can be of one of the four forms, above. (Ugh.)
                # But! con names can also be of the form name1 / name2 / name 3
                #   These are three (or two) different names for the same con.
                # We will assume that there is only limited mixing of these forms!

                @dataclass
                # A simple class for holding an individual convention name from a convention series table, including its link and whether it is <s>cancelled</s> or not
                class ConName:
                    #def __init__(self, Name: str="", Link: str="", Cancelled: bool=False):
                    Name: str=""
                    Cancelled: bool=False
                    Link: str=""

                    def __lt__(self, val: ConName) -> bool:
                        return self.Name < val.Name

                # Take a Wikidot page reference and extract its text and link (if different)
                def SplitConText(constr: str) -> Tuple[str, str]:
                    # Now convert all link|text to separate link and text
                    # Do this for s1 and s2
                    m=re.match("\[\[(.+)\|(.+)]]$", constr)       # Split xxx|yyy into xxx and yyy
                    if m is not None:
                        return m.groups()[0], m.groups()[1]
                    m = re.match("\[\[(.+)]]$", constr)  # Look for a simple [[text]] page reference
                    if m is not None:
                        return "", m.groups()[0]
                    return "", constr

                #----------------------------------------------------------
                # We assume that the cancelled con names precede the uncancelled ones
                # On each call, we find the first con name and return it (as a ConName) and the remaining text as a tuple
                def NibbleCon(constr: str) -> Tuple[Optional[ConName], str]:
                    constr=constr.strip()
                    if len(constr) == 0:
                        return None, constr

                    # We want to take the leading con name
                    # There can be at most one con name which isn't cancelled, and it should be at the end, so first look for a <s>...</s> bracketed con names, if any
                    pat="^<s>(.*?)</s>"
                    m=re.match(pat, constr)
                    if m is not None:
                        s=m.groups()[0]
                        constr=re.sub(pat, "", constr).strip()  # Remove the matched part and trim whitespace
                        l, t=SplitConText(s)
                        con=ConName(Name=t, Link=l, Cancelled=True)
                        return con, constr

                    # OK, there are no <s>...</s> con names left.  So what is left might be [[name]] or [[link|name]]
                    pat="^(\[\[.*?]])"    # Anchored; '[['; non-greedy string of characters; ']]'
                    m=re.match(pat, constr)
                    if m is not None:
                        s=m.groups()[0]     # Get the patched part
                        constr=re.sub(pat, "", constr).strip()  # And remove it fromt he string and trim whitespace
                        l, t=SplitConText(s)           # If text contains a "|" split it on the "|"
                        con=ConName(Name=t, Link=l, Cancelled=False)
                        return con, constr

                    # So far we've found nothing
                    if len(constr) > 0:
                        # If the remaining stuff starts with a colon, return a null result
                        if constr[0] == ":":
                            return None, ""
                        # If it there's a colon later on, the stuff before the colon is a con name.  (Why?)
                        if ":" in constr:
                            constr=constr.split(":")[0]
                        con=ConName(Name=constr)
                        return con, ""

                # Create a list of convention names found along with any attached cancellation/virtual flags and date ranges
                seriesTableRowConEntries: List[Union[ConName, List[ConName]]]=[]
                # Do we have "/" in the con name that is not part of a </s> and not part of a fraction? If so, we have alternate names, not separate cons
                # The strategy here is to recognize the '/' which are *not* con name separators and turn them into '&&&', then split on the remaining '/' and restore the real ones
                def replacer(matchObject) -> str:   # This generates the replacement text when used in a re.sub() call
                    if matchObject.group(1) is not None and matchObject.group(2) is not None:
                        return matchObject.group(1)+"&&&"+matchObject.group(2)
                contextforsplitting=re.sub("(<)/([A-Za-z])", replacer, context)  # Hide the '/' in html items like </xxx>
                contextforsplitting=re.sub("([0-9])/([0-9])", replacer, contextforsplitting)    # Hide the '/' in fractions such as 1/2
                # Split on any remaining '/'s
                contextlist=contextforsplitting.split("/")
                # Restore the '/'s that had been hidden as &&& (and strip, just to be safe)
                contextlist=[x.replace("&&&", "/").strip() for x in contextlist]
                contextlist=[x for x in contextlist if len(x) > 0]  # Squeeze out any empty splits
                if len(contextlist) > 1:
                    alts: List[ConName]=[]
                    for con in contextlist:
                        c, _=NibbleCon(con)
                        if c is not None:
                            alts.append(c)
                    alts.sort()     # Sort the list so that when this list is created from two or more different convention index tables, it looks the same and dups can be removed.
                    seriesTableRowConEntries.append(alts)
                else:
                    # Ok, we have one or more names and they are for different cons
                    while len(context) > 0:
                        con, context=NibbleCon(context)
                        if con is None:
                            break
                        seriesTableRowConEntries.append(con)


                # If the con series table has a location column, extract the text from that cell
                conlocation: Locale=Locale()
                if locColumn is not None:
                    if locColumn < len(row) and len(row[locColumn]) > 0:
                        loc=WikiExtractLink(row[locColumn])     # If there is linked text, get it; otherwise use everything
                        locale=LocaleHandling().ScanForLocale(loc, "")
                        if len(locale) > 0:
                            conlocation=locale[0]

                # Now we have cons and dates and need to create the appropriate convention entries.
                if len(seriesTableRowConEntries) == 0 or len(dates) == 0:
                    Log("Scan abandoned: ncons="+str(len(seriesTableRowConEntries))+"  len(dates)="+str(len(dates)), isError=True)
                    continue

                # Don't add duplicate entries
                def AppendCon(conDict: Dict[str, ConInstanceInfo], cii: ConInstanceInfo) -> None:
                    hits=[x for x in conDict.values() if cii.NameInSeriesList == x.NameInSeriesList and cii.DateRange == x.DateRange and cii.Cancelled == x.Cancelled and cii.Virtual == x.Virtual and cii.Override == x.Override]
                    if len(hits) == 0:
                        # This is a new name: Just append it
                        conDict[cii.NameInSeriesList]=cii
                    elif not cii.Locale.IsEmpty:
                        if hits[0].Locale != cii.Locale:
                            Log("AppendCon:  existing:  "+str(hits[0]))
                            Log("            duplicate - "+str(cii))
                            # Name exists.  But maybe we have some new information on it?
                            # If there are two sources for the convention's location and one is empty, use the other.
                            if hits[0].Locale.IsEmpty:
                                hits[0].Locale=cii.Locale
                                Log("   ...Locale has been updated")

                # The first case we need to look at it whether cons[0] has a type of list of ConInstanceInfo
                # This is one con with multiple names
                if type(seriesTableRowConEntries[0]) is list:
                    # By definition there is only one element. Extract it.  There may be more than one date.
                    assert len(seriesTableRowConEntries) == 1 and len(seriesTableRowConEntries[0]) > 0
                    for dt in dates:
                        override=""
                        cancelled=dt.Cancelled
                        dt.Cancelled = False
                        for co in seriesTableRowConEntries[0]:
                            cancelled=cancelled or co.Cancelled
                            if len(override) > 0:
                                override+=" / "
                            override+="[["
                            if len(co.Link) > 0:
                                override+=co.Link+"|"
                            override+=co.Name+"]]"
                        v = False if cancelled else virtual
                        #TODO: This will cause a name of "dummy" to potentially appear in many cases.  Is this a problem?
                        ci=ConInstanceInfo(_Link="dummy", NameInSeriesList="dummy", Loc=conlocation, DateRange=dt, Virtual=v, Cancelled=cancelled, Override=override)
                        AppendCon(conventions, ci)
                        Log("#append 1: "+str(ci), Print=False)

                # OK, in all the other cases cons is a list[ConInstanceInfo]
                elif len(seriesTableRowConEntries) == len(dates):
                    # Add each con with the corresponding date
                    for i in range(len(seriesTableRowConEntries)):
                        cancelled=seriesTableRowConEntries[i].Cancelled or dates[i].Cancelled
                        dates[i].Cancelled=False    # We've xfered this to ConInstanceInfo and don't still want it here because it would print twice
                        v=False if cancelled else virtual
                        ci=ConInstanceInfo(_Link=seriesTableRowConEntries[i].Link, NameInSeriesList=seriesTableRowConEntries[i].Name, Loc=conlocation, DateRange=dates[i], Virtual=v, Cancelled=cancelled)
                        if ci.DateRange.IsEmpty():
                            Log("***"+ci.Link+"has an empty date range: "+str(ci.DateRange), isError=True)
                        Log("#append 2: "+str(ci), Print=False)
                        AppendCon(conventions, ci)
                elif len(seriesTableRowConEntries) > 1 and len(dates) == 1:
                    # Multiple cons all with the same dates
                    for co in seriesTableRowConEntries:
                        cancelled=co.Cancelled or dates[0].Cancelled
                        dates[0].Cancelled = False
                        v=False if cancelled else virtual
                        ci=ConInstanceInfo(_Link=co.Link, NameInSeriesList=co.Name, Loc=conlocation, DateRange=dates[0], Virtual=v, Cancelled=cancelled)
                        AppendCon(conventions, ci)
                        Log("#append 3: "+str(ci), Print=False)
                elif len(seriesTableRowConEntries) == 1 and len(dates) > 1:
                    for dt in dates:
                        cancelled=seriesTableRowConEntries[0].Cancelled or dt.Cancelled
                        dt.Cancelled = False
                        v=False if cancelled else virtual
                        ci=ConInstanceInfo(_Link=seriesTableRowConEntries[0].Link, NameInSeriesList=seriesTableRowConEntries[0].Name, Loc=conlocation, DateRange=dt, Virtual=v, Cancelled=cancelled)
                        AppendCon(conventions, ci)
                        Log("#append 4: "+str(ci), Print=False)
                else:
                    Log("Can't happen! ncons="+str(len(seriesTableRowConEntries))+"  len(dates)="+str(len(dates)), isError=True)


    # OK, all of the con series have been mined.  Now let's look through all the con instances and see if we can get more location information from them.
    # (Not all con series tables contain location information.)
    # Generate a report of cases where we have non-identical con information from both sources.
    with open("Con location discrepancies.txt", "w+", encoding='utf-8') as f:
        for page in fancyPagesDictByWikiname.values():
            if not page.IsConInstance:
                #Log(f"{page=}")
                continue

            # The page is a convention page
            loc=LocaleHandling().LocaleFromName(page.LocaleStr)
            if not loc.IsEmpty:    # If the page has a Locale set, it overrides
                if page.Name in conventions.keys():
                    conventions[page.Name].Locale=loc
                continue

            # If it's an individual convention page and doesn't have a Locale, we search through its text for something that looks like a placename.
            #TODO: Shouldn't we move this upwards and store the derived location in otherwise-empty page.Locales?
            m=LocaleHandling().ScanConPageforLocale(page.Source, page.Name)
            if m is not None and len(m) > 0:
                for locale in m:
                    # Find the convention in the conventions dictionary and add the location if appropriate.
                    if page.Name in conventions.keys():
                        con=conventions[page.Name]
                        if not locale.LocMatch(con.Locale.PreferredName):
                            if con.Locale.IsEmpty:   # If there previously was no location from the con series page, substitute what we found in the con instance page
                                con.Locale=locale
                                continue
                            f.write(f"{page.Name}: Location mismatch: '{locale.PreferredName}' != '{con.Locale}'\n")


    Log(f"{datetime.now():%H:%M:%S}: Writing: Places that are not tagged as Locales.txt")
    with open("Places that are not tagged as Locales.txt", "w+", encoding='utf-8') as f:
        for key, val in LocaleHandling().probableLocales.items():
            f.write(str(key)+"\n")

    # Normalize convention locations to the standard City, ST form.
    # Log("***Normalizing con locations")
    # for con in conventions.values():
    #     loc=LocaleHandling().ScanConPageforLocale(con.Loc, con.NameInSeriesList)    # TODO: What the hell is this doing??
    #     if len(loc) > 1:
    #         Log("  In "+con.NameInSeriesList+"  found more than one location: "+str(loc))
    #     if len(loc) > 0:
    #         con.Loc=loc[0]    # Nasty code to get one element from the set


    Log(f"{datetime.now():%H:%M:%S}: Writing: Con DateRange oddities.txt")
    oddities=[x for x in conventions.values() if x.DateRange.IsOdd()]
    with open("Con DateRange oddities.txt", "w+", encoding='utf-8') as f:
        for con in oddities:
            f.write(str(con)+"\n")

    # Created a list of conventions sorted in date order from the con dictionary into
    conventionsByDate: List[ConInstanceInfo]=[x for x in conventions.values()]
    conventionsByDate.sort(key=lambda d: d.DateRange)

    #TODO: Add a list of keywords to find and remove.  E.g. "Astra RR" ("Ad Astra XI")

    # ...
    Log(f"{datetime.now():%H:%M:%S}: Writing: Convention timeline (Fancy).txt")
    with open("Convention timeline (Fancy).txt", "w+", encoding='utf-8') as f:
        f.write("This is a chronological list of SF conventions automatically extracted from Fancyclopedia 3\n\n")
        f.write("If a convention is missing from the list, it may be due to it having been added only recently, (this list was generated ")
        f.write(datetime.now().strftime("%A %B %d, %Y  %I:%M:%S %p")+" EST)")
        f.write(" or because we do not yet have information on the convention or because the convention's listing in Fancy 3 is a bit odd ")
        f.write("and the program which creates this list isn't parsing it.  In any case, we welcome help making it more complete!\n\n")
        f.write(f"The list currently has {len(conventions)} conventions.\n")
        currentYear=None
        currentDateRange=None
        # We're going to write a Fancy 3 wiki table
        # Two columns: Daterange and convention name and location
        # The date is not repeated when it is the same
        # The con name and location is crossed out when it was cancelled or moved and (virtual) is added when it was virtual
        f.write("<tab>\n")
        for con in conventionsByDate:
            # Format the convention name and location for tabular output
            if len(con.Override) > 0:
                context=con.Override
            else:
                context="[["+str(con.NameInSeriesList)+"]]"
            if con.Virtual:
                context="''"+context+" (virtual)''"
            else:
                if len(con.Locale.Link) > 0:
                    context+="&nbsp;&nbsp;&nbsp;<small>("+con.Locale.Link+")</small>"

            # Now write the line
            # We have two levels of date headers:  The year and each unique date within the year
            # We do a year header for each new year, so we need to detect when the current year changes
            if currentYear != con.DateRange.StartDate.Year:
                # When the current date range changes, we put the new date range in the 1st column of the table
                currentYear=con.DateRange.StartDate.Year
                currentDateRange=con.DateRange
                f.write('colspan="2"| '+"<big><big>'''"+str(currentYear)+"'''</big></big>\n")

                # Write the row in two halves, first the date column and then the con column
                f.write(f"{con.DateRange}||")
            else:
                if currentDateRange != con.DateRange:
                    f.write(f"{con.DateRange}||")
                    currentDateRange=con.DateRange
                else:
                    f.write("&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;' ' ||")

            if con.Cancelled:
                f.write(f"<s>{context}</s>\n")
            else:
                f.write(context+"\n")


        f.write("</tab>\n")
        f.write("{{conrunning}}\n[[Category:List]]\n")

    # ...
    # OK, now we have a dictionary of all the pages on Fancy 3, which contains all of their outgoing links
    # Build up a dictionary of redirects.  It is indexed by the canonical name of a page and the value is the canonical name of the ultimate redirect
    # Build up an inverse list of all the pages that redirect *to* a given page, also indexed by the page's canonical name. The value here is a list of canonical names.
    Log("***Create inverse redirects tables")
    redirects: Dict[str, str]={}            # Key is the name of a redirect; value is the ultimate destination
    inverseRedirects:Dict[str, List[str]]={}     # Key is the name of a destination page, value is a list of names of pages that redirect to it
    for fancyPage in fancyPagesDictByWikiname.values():
        if fancyPage.Redirect != "":
            redirects[fancyPage.Name]=fancyPage.Redirect
            inverseRedirects.setdefault(fancyPage.Redirect, [])
            inverseRedirects[fancyPage.Redirect].append(fancyPage.Name)
            inverseRedirects.setdefault(fancyPage.Redirect, [])
            if fancyPage.Redirect != fancyPage.Redirect:
                inverseRedirects[fancyPage.Redirect].append(fancyPage.Name)

    # Analyze the Locales
    # Create a list of things that redirect to a Locale, but are not tagged as a locale.
    Log("***Look for things that redirect to a Locale, but are not tagged as a Locale")
    with open("Untagged locales.txt", "w+", encoding='utf-8') as f:
        for fancyPage in fancyPagesDictByWikiname.values():
            if fancyPage.IsLocale:                        # We only care about locales
                if fancyPage.Redirect == "":        # We don't care about redirects
                    if fancyPage.Name in inverseRedirects.keys():
                        for inverse in inverseRedirects[fancyPage.Name]:    # Look at everything that redirects to this
                            if not fancyPagesDictByWikiname[inverse].IsLocale:
                                if "-" not in inverse:                  # If there's a hyphen, it's probably a Wikidot redirect
                                    if inverse[1:] != inverse[1:].lower() and " " in inverse:   # There's a capital letter after the 1st and also a space
                                        f.write(f"{fancyPage.Name} is pointed to by {inverse} which is not a Locale\n")

    # ...
    # Create a dictionary of page references for people pages.
    # The key is a page's canonical name; the value is a list of pages at which they are referenced.
    peopleReferences: Dict[str, List[str]]={}
    Log("***Creating dict of people references")
    for fancyPage in fancyPagesDictByWikiname.values():
        if fancyPage.IsPerson and len(fancyPage.OutgoingReferences) > 0:
            peopleReferences.setdefault(fancyPage.Name, [])
            for outRef in fancyPage.OutgoingReferences:
                if outRef.LinkWikiName in fancyPagesDictByWikiname:
                    if fancyPagesDictByWikiname[outRef.LinkWikiName].IsPerson:
                        peopleReferences.setdefault(outRef.LinkWikiName, [])
                        peopleReferences[outRef.LinkWikiName].append(fancyPage.Name)

    # ...


    ###################################################
    # Now we have a dictionary of all the pages on Fancy 3, which contains all of their outgoing links
    # Build up an inverse list of all the pages that redirect *to* a given page, also indexed by the page's canonical name. The value here is a list of canonical names.
    inverseRedirects: Dict[str, List[str]]={}     # Key is the name of a destination page, value is a list of names of pages that redirect to it
    for fancyPage in fancyPagesDictByWikiname.values():
        if fancyPage.Redirect != "":
            inverseRedirects.setdefault(fancyPage.Redirect, [])
            inverseRedirects[fancyPage.Redirect].append(fancyPage.Name)

    # Create a dictionary of page references for people pages.
    # The key is a page's canonical name; the value is a list of pages at which they are referenced.

    # Go through all outgoing references on the pages and add those which reference a person to that person's list
    peopleReferences: Dict[str, List[str]]={}
    Log("***Creating dict of people references")
    for fancyPage in fancyPagesDictByWikiname.values():
        for outRef in fancyPage.OutgoingReferences:
            if fancyPage.IsPerson:
                peopleReferences.setdefault(outRef.LinkWikiName, [])
                peopleReferences[outRef.LinkWikiName].append(fancyPage.Name)

    Log("***Writing reports")
    # Write out a file containing canonical names, each with a list of pages which refer to it.
    # The format will be
    #     **<canonical name>
    #       <referring page>
    #       <referring page>
    #     ...
    #     **<canonical name>
    #     ...
    Log(f"{datetime.now():%H:%M:%S}: Writing: Referring pages.txt")
    with open("Referring pages.txt", "w+", encoding='utf-8') as f:
        for person, referringpagelist in peopleReferences.items():
            f.write(f"**{person}\n")
            for pagename in referringpagelist:
                f.write(f"  {pagename}\n")

    # Now a list of redirects.
    # We use basically the same format:
    #   **<target page>
    #   <redirect to it>
    #   <redirect to it>
    # ...
    # Now dump the inverse redirects to a file
    Log(f"{datetime.now():%H:%M:%S}: Writing: Redirects.txt")
    with open("Redirects.txt", "w+", encoding='utf-8') as f:
        for redirect, pages in inverseRedirects.items():
            f.write(f"**{redirect}\n")
            for page in pages:
                f.write(f"      ⭦ {page}\n")

    # Next, a list of redirects with a missing target
    Log(f"{datetime.now():%H:%M:%S}: Writing: Redirects with missing target.txt")
    allFancy3Pagenames=set([WindowsFilenameToWikiPagename(n) for n in allFancy3PagesFnames])
    with open("Redirects with missing target 2.txt", "w+", encoding='utf-8') as f:
        for fancyPage in fancyPagesDictByWikiname.values():
            dest=fancyPage.Redirect
            if dest != "" and dest not in allFancy3Pagenames:
                f.write(f"{fancyPage.Name} --> {dest}\n")


    # List pages which are not referred to anywhere and which are not Wikidot redirects
    Log(f"{datetime.now():%H:%M:%S}: Writing: Wikidot redirects with no Mediawiki equivalent.txt")
    with open("Wikidot redirects with no Mediawiki equivalent.txt", "w+", encoding='utf-8') as f:
        setOfWikidotPages=set(x.Name for x in fancyPagesDictByWikiname.values() if x.IsWikidotRedirectPage)
        for page in fancyPagesDictByWikiname.values():
            if not page.IsWikidotRedirectPage:
                wikiname=WikidotCanonicizeName(page.Name)
                if wikiname in setOfWikidotPages:
                    setOfWikidotPages.remove(wikiname)

        listOfOrphanWikidotRedirects=list(setOfWikidotPages)
        for name in listOfOrphanWikidotRedirects:
            print(name, file=f)


    # List pages which are not referred to anywhere and which are not Wikidot redirects
    Log(f"{datetime.now():%H:%M:%S}: Writing: Pages never referred to.txt")
    with open("Pages never referred to.txt", "w+", encoding='utf-8') as f:
        alloutgoingrefs=set([x.LinkWikiName for y in fancyPagesDictByWikiname.values() for x in y.OutgoingReferences])
        alloutgoingrefsF3name=[]
        for x in alloutgoingrefs:
            if x in fancyPagesDictByWikiname.keys():
                alloutgoingrefsF3name.append(x)
        for fancyPage in fancyPagesDictByWikiname.values():
            if fancyPage.IsWikidotRedirectPage:
                continue        # We don't care about these!
            if fancyPage.Name not in alloutgoingrefsF3name:
                f.write(f"{fancyPage.Name}\n")  # We're not OK


    ##################
    # Create and write out a file of peoples' names. They are taken from the titles of pages marked as fan or pro

    # Ambiguous names will often end with something in parenthesis which need to be removed for this particular file
    def RemoveTrailingParens(ss: str) -> str:
        return re.sub("\s\(.*\)$", "", ss)       # Delete any trailing ()


    # Some names are not worth adding to the list of people names.  Try to detect them.
    def IsInterestingName(p: str) -> bool:
        if " " not in p and "-" in p:   # We want to ignore names like "Bob-Tucker" in favor of "Bob Tucker"
            return False
        if " " in p:                    # If there are spaces in the name, at least one of them needs to be followed by a UC letter
            if re.search(" ([A-Z]|de|ha|von|Č)", p) is None:  # We want to ignore "Bob tucker", so we insist that there is a space in the name followed by
                                                              # a capital letter, "de", "ha", "von" orČ.  I.e., there is a last name that isn't all lower case.
                                                              # (All lower case after the 1st letter indicates its an auto-generated redirect of some sort.)
                return False
        return True



    Log(f"{datetime.now():%H:%M:%S}: Writing: Peoples rejected names.txt")
    peopleNames: List[str]=[]
    # Go through the list of all the pages labelled as Person
    # Build a list of people's names
    with open("Peoples rejected names.txt", "w+", encoding='utf-8') as f:
        for fancyPage in fancyPagesDictByWikiname.values():
            if fancyPage.IsPerson:
                peopleNames.append(RemoveTrailingParens(fancyPage.Name))
                # Then all the redirects to one of those pages.
                if fancyPage.Name in inverseRedirects.keys():
                    for p in inverseRedirects[fancyPage.Name]:
                        if p in fancyPagesDictByWikiname.keys():
                            peopleNames.append(RemoveTrailingParens(fancyPagesDictByWikiname[p].Redirect))
                            if IsInterestingName(p):
                                peopleNames.append(p)
                            else:
                                f.write(f"Uninteresting: {p}\n")
                        else:
                            Log(p+" does not point to a person's name")
                else:
                    f.write(f"{fancyPage.Name}: Good name -- ignored\n")


    # De-dupe it
    peopleNames=list(set(peopleNames))

    # Create and write out a file of peoples' names. They are taken from the titles of pages marked as fan or pro
    Log(f"{datetime.now():%H:%M:%S}: Writing: Peoples names.txt")
    with open("Peoples names.txt", "w+", encoding='utf-8') as f:
        peopleNames.sort(key=lambda p: p.split()[-1][0].upper()+p.split()[-1][1:]+","+" ".join(p.split()[0:-1]))    # Invert so that last name is first and make initial letter UC.
        for name in peopleNames:
            f.write(name+"\n")

    # Create some reports on tags/Categories
    adminTags={"Admin", "mlo", "jrb", "Nofiles", "Nodates", "Nostart", "Noseries", "Noend", "Nowebsite", "Hasfiles", "Haslink", "Haswebsite", "Fixme", "Details", "Redirect", "Wikidot", "Multiple",
               "Choice", "Iframe", "Active", "Inactive", "IA", "Map", "Mapped", "Nocountry", "Noend", "Validated"}
    countryTags={"US", "UK", "Australia", "Ireland", "Europe", "Asia", "Canada"}
    ignoredTags=adminTags.copy()
    ignoredTags.union({"Fancy1", "Fancy2"})

    def ComputeTagCounts(pageDict: Dict[str, F3Page], ignoredTags: set) -> Tuple[Dict[str, int], Dict[str, int]]:
        tagcounts: Dict[str, int]={}
        tagsetcounts: Dict[str, int]={"notags": 0}
        for fp in pageDict.values():
            if not fp.IsRedirectpage:
                tagset=TagSet()
                tags=fp.Tags
                if len(tags) > 0:
                    for tag in tags:
                        if tag not in ignoredTags:
                            tagset.add(tag)
                        tagcounts.setdefault(tag, 0)
                        tagcounts[tag]+=1
                    tagsetcounts.setdefault(str(tagset), 0)
                    tagsetcounts[str(tagset)]+=1
                else:
                    tagsetcounts["notags"]+=1
        return tagcounts, tagsetcounts

    tagcounts, tagsetcounts=ComputeTagCounts(fancyPagesDictByWikiname, ignoredTags)

    Log(f"{datetime.now():%H:%M:%S}: Writing: Counts for individual tags.txt")
    with open("Tag counts.txt", "w+", encoding='utf-8') as f:
        tagcountslist=[(key, val) for key, val in tagcounts.items()]
        tagcountslist.sort(key=lambda elem: elem[1], reverse=True)
        for tag, count in tagcountslist:
            f.write(f"{tag}: {count}\n")

    Log(f"{datetime.now():%H:%M:%S}: Writing: Counts for tagsets.txt")
    with open("Tagset counts.txt", "w+", encoding='utf-8') as f:
        tagsetcountslist=[(key, val) for key, val in tagsetcounts.items()]
        tagsetcountslist.sort(key=lambda elem: elem[1], reverse=True)
        for tagset, count in tagsetcountslist:
            f.write(f"{tagset}: {count}\n")

    ##################
    # Now redo the counts, ignoring countries
    ignoredTags=adminTags.copy().union(countryTags)
    tagcounts, tagsetcounts=ComputeTagCounts(fancyPagesDictByWikiname, ignoredTags)

    Log(f"{datetime.now():%H:%M:%S}: Writing: Counts for tagsets without country.txt")
    with open("Tagset counts without country.txt", "w+", encoding='utf-8') as f:
        for tagset, count in tagsetcounts.items():
            f.write(f"{tagset}: {count}\n")


    ##################
    # Now do it again, but this time look at all subsets of the tags (again, ignoring the admin tags)
    tagsetcounts: Dict[str, int]={}
    for fp in fancyPagesDictByWikiname.values():
        if not fp.IsRedirectpage:
            tagpowerset=set()   # of TagSets
            tags=fp.Tags
            # The power set is a set of all the subsets.
            # For each tag, we double the power set by adding a copy of itself with that tag added to each of the previous sets
            for tag in tags:
                if tag not in ignoredTags:
                    if len(tagpowerset) > 0:
                        # Duplicate and extend any existing TagSets
                        temptagpowerset=tagpowerset.copy()
                        for st in temptagpowerset:
                            st.add(tag)
                        tagpowerset=tagpowerset.union(temptagpowerset)
                    tagpowerset.add(TagSet(tag))  # Then add a TagSet consisting of just the tag, also
            # Now run through all the members of the power set, incrementing the global counts
            for ts in tagpowerset:
                tagsetcounts.setdefault(str(ts), 0)
                tagsetcounts[str(ts)]+=1

    Log(f"{datetime.now():%H:%M:%S}: Writing: Counts for tagpowersets.txt")
    with open("Tagpowerset counts.txt", "w+", encoding='utf-8') as f:
        for tagset, count in tagsetcounts.items():
            f.write(f"{tagset}: {count}\n")

    ##############
    # We want apazine and clubzine to be used in addition to fanzine.  Make a list of
    # First make a list of all the pages labelled as "fan" or "pro"
    Log(f"{datetime.now():%H:%M:%S}: Writing: Apazines and clubzines that aren't fanzines.txt")
    with open("Apazines and clubzines that aren't fanzines.txt", "w+", encoding='utf-8') as f:
        for fancyPage in fancyPagesDictByWikiname.values():
            # Then all the redirects to one of those pages.
            if ("Apazine" in fancyPage.Tags or "Clubzine" in fancyPage.Tags) and "Fanzine" not in fancyPage.Tags:
                f.write(fancyPage.Name+"\n")


    ##################
    # Make a list of all all-upper-case pages which are not tagged initialism.
    Log(f"{datetime.now():%H:%M:%S}: Writing: Uppercase name which aren't marked as Initialisms.txt")
    with open("Uppercase names which aren't marked as initialisms.txt", "w+", encoding='utf-8') as f:
        for fancyPage in fancyPagesDictByWikiname.values():
            # A page might be an initialism if ALL alpha characters are upper case
            if fancyPage.Name == fancyPage.Name.upper():
                fpn=fancyPage.Name
                # Bail out if it starts with 4 digits -- this is probably a year
                if fpn[:4].isnumeric():
                    continue
                # Also bail if it begin 'nn which is also likely a year (e.g., '73)
                if fpn[0] == "'" and fpn[1:3].isnumeric():
                    continue
                # We skip certain pages because while they may look like initilaisms, they aren't or because we only flag con series, and not the individual cons
                ignorelist: List[str]=["DSC", "CAN*CON", "ICFA", "NJAC", "OASIS", "OVFF", "URCON", "VCON"]
                if any([fpn.startswith(x+" ") for x in ignorelist]):
                    continue
                # Bail if there are no alphabetic characters at all
                if fpn.lower() == fpn.upper():
                    continue

                # If what's left lacks the Initialism tag, we want to list it
                if "Initialism" not in fancyPage.Tags:
                    f.write(fancyPage.Name+": "+str(fancyPage.Tags)+"\n")


    ##################
    # Tagging Oddities
    # Make lists of odd tag combinations which may indicate something wrong
    Log("Tagging oddities.txt")

    def WriteSelectedTags(fancyPagesDictByWikiname: Dict[str, F3Page], select, f):
        f.write("-------------------------------------------------------\n")
        found=False
        for fancyPage in fancyPagesDictByWikiname.values():
            if select(fancyPage):
                found=True
                f.write(f"{fancyPage.Name}: {fancyPage.Tags}\n")
        if not found:
            f.write("(none found)\n")

    with open("Tagging oddities.txt", "w+", encoding='utf-8') as f:
        f.write("-------------------------------------------------------\n")
        f.write("Fans, Pros, and Mundanes who are not also tagged person\n")
        WriteSelectedTags(fancyPagesDictByWikiname, lambda fp: ("Pro" in fp.Tags or "Mundane" in fp.Tags or "Fan" in fp.Tags) and "Person" not in fp.Tags, f)

        f.write("\n\n-------------------------------------------------------\n")
        f.write("Persons who are not tagged Fan, Pro, or Mundane\n")
        WriteSelectedTags(fancyPagesDictByWikiname, lambda fp:"Person" in fp.Tags and "Fan" not in fp.Tags and "Pro" not in fp.Tags and "Mundane" not in fp.Tags, f)

        f.write("\n\n-------------------------------------------------------\n")
        f.write("Publishers which are tagged as persons\n")
        WriteSelectedTags(fancyPagesDictByWikiname, lambda fp: fp.IsPublisher and fp.IsPerson, f)

        f.write("\n\n-------------------------------------------------------\n")
        f.write("Nicknames which are not persons, fanzines or cons\n")
        WriteSelectedTags(fancyPagesDictByWikiname, lambda fp: fp.IsNickname and not (fp.IsPerson or fp.IsFanzine or fp.IsConInstance), f)

        f.write("\n\n-------------------------------------------------------\n")
        f.write("Pages with both 'Inseries' and 'Conseries'\n")
        WriteSelectedTags(fancyPagesDictByWikiname, lambda fp: "Inseries" in fp.Tags and "Conseries" in fp.Tags, f)

        f.write("\n\n-------------------------------------------------------\n")
        f.write("Pages with 'Convention' but neither 'Inseries' or 'Conseries' or 'Onetimecon'\n")
        WriteSelectedTags(fancyPagesDictByWikiname, lambda fp: "Convention" in fp.Tags and not ("Inseries" in fp.Tags or "Conseries" in fp.Tags or "Onetimecon" in fp.Tags), f)


    ##################
    # Make a list of all Mundanes
    Log(f"{datetime.now():%H:%M:%S}: Writing: Mundanes.txt")
    with open("Mundanes.txt", "w+", encoding='utf-8') as f:
        for fancyPage in fancyPagesDictByWikiname.values():
            # Then all the redirects to one of those pages.
            if fancyPage.IsMundane:
                f.write(f"{fancyPage.Name}: {fancyPage.Tags}\n")

    ##################
    # Compute some special statistics to display at fanac.org
    Log(f"{datetime.now():%H:%M:%S}: Writing: Statistics.txt")
    with open("Statistics.txt", "w+", encoding='utf-8') as f:
        npages=0            # Number of real (non-redirect) pages
        npeople=0           # Number of people
        nfans=0
        nconinstances=0     # Number of convention instances
        nfanzines=0         # Number of fanzines of all sorts
        napas=0             # Number of APAs
        nclubs=0            # Number of clubs
        for fancyPage in fancyPagesDictByWikiname.values():
            if not fancyPage.IsRedirectpage:
                npages+=1
                if fancyPage.IsPerson:
                    npeople+=1
                if fancyPage.IsFan:
                    nfans+=1
                if fancyPage.IsFanzine:
                    nfanzines+=1
                if fancyPage.IsAPA:
                    napas+=1
                if fancyPage.IsClub:
                    nclubs+=1
                if fancyPage.IsConInstance:
                    nconinstances+=1
        f.write("Unique (ignoring redirects)\n")
        f.write(f"  Total pages: {npages}\n")
        f.write(f"  All people: {npeople}\n")
        f.write(f"  Fans: {nfans}\n")
        f.write(f"  Fanzines: {nfanzines}\n")
        f.write(f"  APAs: {napas}\n")
        f.write(f"  Club: {nclubs}\n")
        f.write(f"  Conventions: {nconinstances}\n")



if __name__ == "__main__":
    main()

