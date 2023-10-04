from typing import Optional, Union

import os
import re
from datetime import datetime
from collections import defaultdict

from LocalePage import LocaleHandling, LocalePage
from F3Page import F3Page, DigestPage, TagSet
from Log import Log, LogOpen, LogSetHeader
from HelpersPackage import WindowsFilenameToWikiPagename, WikiExtractLink, CrosscheckListElement, ScanForBracketedText, WikidotCanonicizeName, StripWikiBrackets
from HelpersPackage import CompressWhitespace, ConvertHTMLishCharacters
from ConInstanceInfo import ConInstanceInfo, ConInstanceLink
from FanzineIssueSpecPackage import FanzineDateRange, FanzineDate


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
    Log("***Querying the local copy of Fancy 3 to create a list of all Fancyclopedia pages", timestamp=True)
    Log("   path='"+fancySitePath+"'")
    #allFancy3PagesFnames = [f[:-4] for f in os.listdir(fancySitePath) if os.path.isfile(os.path.join(fancySitePath, f)) and f.endswith(".txt")]
    allFancy3PagesFnames = [f[:-4] for f in os.listdir(fancySitePath) if  f.endswith(".txt")]
    allFancy3PagesFnames = [f for f in allFancy3PagesFnames if not f.startswith("index_")]     # Drop index pages
    allFancy3PagesFnames = [f for f in allFancy3PagesFnames if not f.endswith(".js")]     # Drop javascript page

    # The following lines are for debugging and are used to select a subset of the pages for greater speed
    #allFancy3PagesFnames= [f for f in allFancy3PagesFnames if f[0] in "A"]        # Just to cut down the number of pages for debugging purposes
    #allFancy3PagesFnames= [f for f in allFancy3PagesFnames if f.lower().startswith(("miscon", "misc^^on"))]        # Just to cut down the number of pages for debugging purposes
    #allFancy3PagesFnames= [f for f in allFancy3PagesFnames if f.lower().startswith("eurocon")]        # Just to cut down the number of pages for debugging purposes
    #allFancy3PagesFnames=["Early Conventions"]

    # We ignore pages with certain prefixes
    excludedPrefixes=("_admin", "Template;colon", "User;colon", "Log 2")
    allFancy3PagesFnames = [f for f in allFancy3PagesFnames if not f.startswith(excludedPrefixes)]

    # And we exclude certain specific pages
    excludedPages=["Admin", "Standards", "Test Templates"]
    allFancy3PagesFnames=[f for f in allFancy3PagesFnames if f not in excludedPages]
    Log("   "+str(len(allFancy3PagesFnames))+" pages found")

    # The master dictionary of all Fancy 3 pages.
    fancyPagesDictByWikiname: dict[str, F3Page]={}     # Key is page's name on the wiki; Value is a F3Page class containing all the references, tags, etc. on the page

    Log("***Scanning local copies of pages for links and other info", timestamp=True)
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


    Log("Writing: Redirects to Wikidot pages.txt", timestamp=True)
    with open("Redirects to Wikidot pages.txt", "w+", encoding='utf-8') as f:
        for key, val in fancyPagesDictByWikiname.items():
            for link in val.OutgoingReferences:
                if link.LinkWikiName in fancyPagesDictByWikiname.keys():
                    if fancyPagesDictByWikiname[link.LinkWikiName].IsWikidotRedirectPage:
                        print(f"Page '{key}' has a pointer to Wikidot redirect page '{link.LinkWikiName}'", file=f)


    # Build a locale database
    Log("***Building a locale dictionary", timestamp=True)
    LocaleHandling().Create(fancyPagesDictByWikiname)

    Log("***Analyzing convention series tables", Clear=True, timestamp=True)

    # Scan for a virtual flag
    # Return True/False and remaining text after V-flag is removed
    def ScanForVirtual(s: str) -> tuple[bool, str]:
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
    conventions: defaultdict[str, list[ConInstanceInfo]]=defaultdict(list)
    for page in fancyPagesDictByWikiname.values():

        # First, see if this is a Conseries page
        if not page.IsConSeries:
            continue

        LogSetHeader("Processing "+page.Name)

        # Sometimes there will be multiple tables, so we check each of them
        for index, table in enumerate(page.Tables):
            numcolumns=len(table.Headers)

            locColumn=CrosscheckListElement(["Locations", "Location"], table.Headers)
            # We don't log a missing location column because that is common and not an error -- we'll try to get the location later from the con instance's page

            conColumn=CrosscheckListElement(["Convention", "Convention Name", "Name"], table.Headers)
            if conColumn is None:
                Log("***Can't find Convention column in table "+str(index+1)+" of "+str(len(page.Tables)), isError=True, Print=False)
                continue

            dateColumn=CrosscheckListElement(["Date", "Dates"], table.Headers)
            if dateColumn is None:
                Log("***Can't find Dates column in table "+str(index+1)+" of "+str(len(page.Tables)), isError=True, Print=False)
                continue

            # Make sure the table has rows
            if table.Rows is None:
                Log(f"***Table {index+1} of {len(page.Tables)} looks like a convention table, but has no rows", isError=True, Print=False)
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
                Log(f"{virtual=}", Print=False)

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

                #............................
                # First the date column
                datetext = row[dateColumn]

                # For the dates column, we want to remove the virtual designation as it will just confuse later processing.
                # We want to handle the case where (virtual) is in parens, but also when it isn't.
                # We need two patterns here because Python's regex doesn't have balancing groups and we don't want to match unbalanced parens

                # Ignore anything in trailing parenthesis. (e.g, "(Easter weekend)", "(Memorial Day)")
                datetext=re.sub("\(.*\)\s?$", "", datetext)   # Note that this is greedy. Is that the correct things to do?
                # Convert the HTML characters some people have inserted into their ascii equivalents
                datetext=CompressWhitespace(datetext)
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
                dates:list[FanzineDateRange]=[]
                for d in ds:
                    if len(d) > 0:
                        c, s=ScanForBracketedText(d, "s")
                        dr=FanzineDateRange().Match(s)
                        dr.Cancelled=c
                        if dr.Duration() > 7:
                            Log("??? convention has long duration: "+str(dr), isError=True, Print=False)
                        if not dr.IsEmpty():
                            dates.append(dr)

                if len(dates) == 0:
                    Log(f"***No dates found - {page.Name}:  {datetext=}  {row=}", isError=True, Print=False)
                elif len(dates) == 1:
                    Log(f"{page.Name}  row: {row}: 1 date: {dates[0]}", Print=False)
                else:
                    Log(f"{page.Name}  row: {row}: {len(dates)} dates: {dates[0]}", Print=False)
                    for d in dates[1:]:
                        Log(f"           {d}", Print=False)


                #............................................
                # Now handle the names column
                # Get the corresponding convention name(s).
                nameText=row[conColumn]
                # Clean up the text
                # Convert the HTML characters some people have inserted into their ascii equivalents
                nameText=ConvertHTMLishCharacters(nameText)
                # And get rid of hard line breaks
                nameText=nameText.replace("<br>", " ")
                # In some pages we italicize or bold the con's name, so remove spans of single quotes of length 2 or longer
                nameText=re.sub("[']{2,}", "", nameText)

                nameText=nameText.strip()

                if nameText.count("[[") != nameText.count("]]"):
                    Log("'"+row[conColumn]+"' has unbalanced double brackets. This is unlikely to end well...", isError=True)

                # An individual name is of one of these forms:
                    #   xxx
                    # [[xxx]] zzz               Ignore the "zzz"
                    # [[xxx|yyy]]               Use just xxx
                    # [[xxx|yyy]] zzz           Ignore the zzz
                # An individual name can be cancelled:
                    # <s>name</s>
                # A convention can have multiple actual alternative names of the form name1 / name2 / name 3
                    # These are two or three different names for the same con.
                    # A typical case is where a con is part of multiple series at once, e.g., a DeepSouthCon held with a local con
                # Note the distinction between multiple cons and multiple names for the same con.  The "/" is the distinguishing mark

                # When the name text has multiple con names that are not alternatives, they may match multiple dates in the date column, like when a
                # a con converted from real to virtual while changing its name and keeping its dates:
                    # E.g., <s>[[FilKONtario 30]]</s> [[FilKONtari-NO]] (trailing stuff)

                # Whatcon 20: This Year's Theme -- need to split on the colon and ignore the rest

                # We will assume that there is only limited mixing of these forms!  E.g., a con with multiple names is either cancelled altogether or not cancelled.

                # Take a Wikidot page reference and extract its text and link (if different)
                # Return them as (link, text)
                def SplitNametext(constr: str) -> tuple[str, str]:
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
                def NibbleConNametext(connamestr: str) -> tuple[Optional[ConInstanceLink], str]:
                    connamestr=connamestr.strip()
                    if len(connamestr) == 0:
                        return None, connamestr

                    # Change 'name: stuff' into just 'name'
                    def DeColonize(name: str) -> str:
                        if len(name) == 0:
                            return ""
                        if name[0] == ":":  # A name starting with a colon is the leftover from a fully processed name with :stuff following it
                            return ""
                        # If there's a colon, return the stuff before the colon
                        if ":" in name:
                            return name.split(":")[0].strip()
                        return name

                    # We want to take the leading con name
                    # There can be at most one con name which isn't cancelled, and it should be at the end, so first look for a <s>...</s> bracketed con names, if any
                    pat="^<s>(.*?)</s>"     # Note that .*? is non-greedy
                    m=re.match(pat, connamestr)
                    if m is not None:
                        s=m.groups()[0]
                        connamestr=re.sub(pat, "", connamestr).strip()  # Remove the matched part and trim whitespace
                        s=DeColonize(s)
                        l, t=SplitNametext(s)
                        con=ConInstanceLink(Text=t, Link=l, Cancelled=True)
                        return con, connamestr

                    # OK, there are no <s>...</s> con names left.  So what is left might be [[name]] or [[link|name]]
                    pat="^(\[\[.*?]])"    # Anchored; '[['; non-greedy string of characters; ']]'
                    m=re.match(pat, connamestr)
                    if m is not None:
                        s=m.groups()[0]     # Get the patched part
                        connamestr=re.sub(pat, "", connamestr).strip()  # And remove it from the string and trim whitespace
                        s=DeColonize(s)
                        l, t=SplitNametext(s)           # If text contains a "|" split it on the "|"
                        con=ConInstanceLink(Text=t, Link=l, Cancelled=False)
                        return con, connamestr

                    # So far we've found nothing
                    if len(connamestr) > 0:
                        connamestr=DeColonize(connamestr)
                        if len(connamestr) == 0:
                            return None, ""
                        con=ConInstanceLink(Text=connamestr)
                        return con, ""

                # Create a list of convention names found along with any attached cancellation/virtual flags and date ranges
                seriesTableRowConEntries: list[ConInstanceLink | list[ConInstanceLink]]=[]
                # Do we have "/" in the con name that is not part of a </s> and not part of a fraction? If so, we have alternate names, not separate cons
                # The strategy here is to recognize the '/' which are *not* con name separators and turn them into '&&&', then split on the remaining '/' and restore the real ones
                def replacer(matchObject) -> str:   # This generates the replacement text when used in a re.sub() call
                    if matchObject.group(1) is not None and matchObject.group(2) is not None:
                        return matchObject.group(1)+"&&&"+matchObject.group(2)
                contextforsplitting=re.sub("(<)/([A-Za-z])", replacer, nameText)  # Hide the '/' in html items like </xxx>
                contextforsplitting=re.sub("([0-9])/([0-9])", replacer, contextforsplitting)    # Hide the '/' in fractions such as 1/2
                # Split on any remaining '/'s
                contextlist=contextforsplitting.split("/")
                # Restore the '/'s that had been hidden as &&& (and strip, just to be safe)
                contextlist=[x.replace("&&&", "/").strip() for x in contextlist]
                contextlist=[x for x in contextlist if len(x) > 0]  # Squeeze out any empty splits
                if len(contextlist) > 1:
                    alts: list[ConInstanceLink]=[]
                    for con in contextlist:
                        c, _=NibbleConNametext(con)
                        if c is not None:
                            alts.append(c)
                    alts.sort()     # Sort the list so that when this list is created from two or more different convention index tables, it looks the same and dups can be removed.
                    seriesTableRowConEntries.append(alts)
                else:
                    # Ok, we have one or more names and they are for different cons
                    while len(nameText) > 0:
                        con, nameText=NibbleConNametext(nameText)
                        if con is None:
                            break
                        seriesTableRowConEntries.append(con)


                # If the con series table has a location column, extract the text from that cell
                conlocation: LocalePage=LocalePage()
                if locColumn is not None:
                    if locColumn < len(row) and len(row[locColumn]) > 0:
                        loc=WikiExtractLink(row[locColumn])     # If there is linked text, get it; otherwise use everything
                        locale=LocaleHandling().ScanForLocale(loc, page.Name)
                        if len(locale) > 0:
                            conlocation=locale[0]

                # Now we have cons and dates and need to create the appropriate convention entries.
                if len(seriesTableRowConEntries) == 0 or len(dates) == 0:
                    Log("Scan abandoned: ncons="+str(len(seriesTableRowConEntries))+"  len(dates)="+str(len(dates)), isError=True, Print=False)
                    continue

                # Don't add duplicate entries to the conlist
                def AppendCon(conDict: defaultdict[str, list[ConInstanceInfo]], cii: ConInstanceInfo) -> None:
                    hits=[y for x in conDict.values() for y in x if cii == y]
                    if len(hits) == 0:
                        # This is a new name: Just append it
                        conDict[cii.Name].append(cii)
                    elif not cii.LocalePage.IsEmpty:
                        if hits[0].LocalePage != cii.LocalePage:
                            Log("AppendCon:  existing:  "+str(hits[0]), isError=True, Print=False)
                            Log("            duplicate - "+str(cii), isError=True, Print=False)
                            # Name exists.  But maybe we have some new information on it?
                            # If there are two sources for the convention's location and one is empty, use the other.
                            if hits[0].LocalePage.IsEmpty:
                                hits[0].LocalePage=cii.LocalePage
                                Log("   ...Locale has been updated", isError=True, Print=False)

                # The first case we need to look at it whether cons[0] has a type of list of ConInstanceInfo
                # This is one con with multiple names
                if type(seriesTableRowConEntries[0]) is list:
                    # Log(f"Case 1: {len(seriesTableRowConEntries[0])=}")
                    # for i in range(len(seriesTableRowConEntries[0])):
                    #     Log(f"             {str(seriesTableRowConEntries[0][i])}")
                    # Log(f"         {len(dates)=}")
                    # Log(f"         {str(dates[0])=}")
                    # By definition there is only one element. Extract it.  There may be more than one date.
                    assert len(seriesTableRowConEntries) == 1 and len(seriesTableRowConEntries[0]) > 0
                    links=[]
                    names=[]
                    cancelled=False
                    for co in seriesTableRowConEntries[0]:
                        links.append(co.Link)
                        names.append(co.Text)
                        cancelled=cancelled or co.Cancelled

                    for dt in dates:
                        cancelled=cancelled or dt.Cancelled
                        v = False if cancelled else virtual
                        for dt in dates:
                            ci=ConInstanceInfo(Link=links, Text=names, Locale=conlocation, DateRange=dt, Virtual=False if cancelled else virtual, Cancelled=dt.Cancelled, SeriesName=page.Name)
                            AppendCon(conventions, ci)
                            Log(f"#append 1: {ci}", Print=False)

                # OK, in all the other cases cons is a list[ConInstanceInfo]
                elif len(seriesTableRowConEntries) == len(dates):
                    # Log(f"Case 2: {len(seriesTableRowConEntries)=}")
                    # for i in range(len(seriesTableRowConEntries)):
                    #     Log(f"             {str(seriesTableRowConEntries[i])}")
                    # Log(f"         {len(dates)=}")
                    # for i in range(len(dates)):
                    #     Log(f"             {str(dates[i])=}")
                    # Add each con with the corresponding date
                    for i in range(len(seriesTableRowConEntries)):
                        cancelled=seriesTableRowConEntries[i].Cancelled or dates[i].Cancelled
                        dates[i].Cancelled=False    # We've xfered this to ConInstanceInfo and don't still want it here because it would print twice
                        v=False if cancelled else virtual
                        ci=ConInstanceInfo(Link=seriesTableRowConEntries[i].Link, Text=seriesTableRowConEntries[i].Text, Locale=conlocation, DateRange=dates[i], Virtual=v, Cancelled=cancelled, SeriesName=page.Name)
                        if ci.DateRange.IsEmpty():
                            Log(f"***{ci.Link} has an empty date range: {ci.DateRange}", isError=True)
                        Log(f"#append 2: {ci}", Print=False)
                        AppendCon(conventions, ci)

                elif len(seriesTableRowConEntries) > 1 and len(dates) == 1:
                    # Log(f"Case 3: {len(seriesTableRowConEntries)=}")
                    # for i in range(len(seriesTableRowConEntries)):
                    #     Log(f"             {str(seriesTableRowConEntries[i])}")
                    # Log(f"         {len(dates)=}")
                    # Log(f"         {str(dates[0])=}")
                    # Multiple cons all with the same dates
                    for co in seriesTableRowConEntries:
                        cancelled=co.Cancelled or dates[0].Cancelled
                        dates[0].Cancelled = False
                        v=False if cancelled else virtual
                        ci=ConInstanceInfo(Link=co.Link, Text=co.Text, Locale=conlocation, DateRange=dates[0], Virtual=v, Cancelled=cancelled, SeriesName=page.Name)
                        AppendCon(conventions, ci)
                        Log(f"#append 3: {ci}", Print=False)

                elif len(seriesTableRowConEntries) == 1 and len(dates) > 1:
                    # Log(f"Case 4: {len(seriesTableRowConEntries[0])=}")
                    # for i in range(len(seriesTableRowConEntries[0])):
                    #     Log(f"             {str(seriesTableRowConEntries[0][i])}")
                    # Log(f"         {len(dates)=}")
                    # for i in range(len(dates)):
                    #     Log(f"             {str(dates[0][i])=}")
                    for dt in dates:
                        cancelled=seriesTableRowConEntries[0].Cancelled or dt.Cancelled
                        dt.Cancelled = False
                        v=False if cancelled else virtual
                        ci=ConInstanceInfo(Link=seriesTableRowConEntries[0].Link, Text=seriesTableRowConEntries[0].Text, Locale=conlocation, DateRange=dt, Virtual=v, Cancelled=cancelled, SeriesName=page.Name)
                        AppendCon(conventions, ci)
                        Log(f"#append 4: {ci}", Print=False)

                else:
                    # We really should deal with the case of Westercon 75/Loscon 49... What an ugly mess!
                    Log(f"Shouldn't happen! ncons={len(seriesTableRowConEntries)}  {len(dates)=}", isError=True)


    # OK, all of the con series have been mined.  Now let's look through all the con instances and see if we can get more location information from them.
    # (Not all con series tables contain location information.)
    # Generate a report of cases where we have non-identical con information from both sources.
    with open("Con location discrepancies.txt", "w+", encoding='utf-8') as f:
        for page in fancyPagesDictByWikiname.values():

            if not page.IsConInstance:
                #Log(f"Not  a con instance: {page=}")
                continue

            Log(f" {page.Name=}")

            # The page is a convention page
            loc=LocaleHandling().LocaleFromName(page.LocaleStr)
            # If the page has a Locale set, it overrides any internal data
            if not loc.IsEmpty:
                if page.Name not in conventions.keys():
                    f.write(f"{page.Name} not in conventions.keys()\n")
                    continue
                for con in conventions[page.Name]:
                    con.Locale=loc        #TODO: We really ought to locate the specific con in the list
                continue

            # If it's an individual convention page and doesn't have a Locale, we search through its text for something that looks like a placename.
            #TODO: Shouldn't we move this upwards and store the derived location in otherwise-empty page.Locales?
            m=LocaleHandling().ScanConPageforLocale(page.Source, page.Name)
            if m is not None and len(m) > 0:
                for locale in m:
                    # Find the convention in the conventions dictionary and add the location if appropriate.
                    if page.Name in conventions.keys():
                        for con in conventions[page.Name]:
                            if not locale.LocMatch(con.LocalePage.PreferredName):
                                if con.LocalePage.IsEmpty:   # If there previously was no location from the con series page, substitute what we found in the con instance page
                                    con.LocalePage=locale
                                    continue
                                f.write(f"{page.Name}: Location mismatch: '{locale.PreferredName}' != '{con.LocalePage}'\n")


    Log("Writing: Places that are not tagged as Locales.txt", timestamp=True)
    with open("Places that are not tagged as Locales.txt", "w+", encoding='utf-8') as f:
        for key, val in LocaleHandling().probableLocales.items():
            f.write(str(key)+"\n")

    # Normalize convention locations to the standard City, ST form.
    # Log("***Normalizing con locations")
    # for con in conventions.values():
    #     loc=LocaleHandling().ScanConPageforLocale(con.Loc, con.Text)    # TODO: What the hell is this doing??
    #     if len(loc) > 1:
    #         Log("  In "+con.Text+"  found more than one location: "+str(loc))
    #     if len(loc) > 0:
    #         con.Loc=loc[0]    # Nasty code to get one element from the set


    Log("Writing: Con DateRange oddities.txt", timestamp=True)
    oddities=[y for x in conventions.values() for y in x if y.DateRange.IsOdd()]
    with open("Con DateRange oddities.txt", "w+", encoding='utf-8') as f:
        for con in oddities:
            f.write(str(con)+"\n")

    # Created a list of conventions sorted in date order from the con dictionary into
    conventionsByDate: list[ConInstanceInfo]=[y for x in conventions.values() for y in x]
    conventionsByDate.sort(key=lambda d: d.Text)
    conventionsByDate.sort(key=lambda d: d.DateRange)

    #TODO: Add a list of keywords to find and remove.  E.g. "Astra RR" ("Ad Astra XI")

    # ...
    Log("Writing: Convention timeline (Fancy).txt", timestamp=True)
    with open("Convention timeline (Fancy).txt", "w+", encoding='utf-8') as f:
        f.write("This is a chronological list of SF conventions automatically extracted from Fancyclopedia 3\n\n")
        f.write("If a convention is missing from the list, we may not know about it or it may have been added only recently, (this list was generated ")
        f.write(datetime.now().strftime("%A %B %d, %Y  %I:%M:%S %p")+" EST)")
        f.write(" or because we do not yet have information on the convention or because the convention's listing in Fancy 3 is a bit odd ")
        f.write("and the program which creates this list isn't parsing it.  In any case, we welcome help making it more complete!\n\n")
        f.write(f"The list currently has {sum([len(x) for x in conventions.values()])} conventions.\n")
        currentYear=None
        currentDateRange=None
        # We're going to write a Fancy 3 wiki table
        # Two columns: Daterange and convention name and location
        # The date is not repeated when it is the same
        # The con name and location is crossed out when it was cancelled or moved and (virtual) is added when it was virtual
        f.write("<tab>\n")
        lastcon: ConInstanceInfo=ConInstanceInfo()
        for con in conventionsByDate:

            # When a con has multiple names and is written line this
            #       [[DeepSouthCon 58]] / [[ConGregate 2020]]
            # it shows up twice in the list of cons, but in both cases the proper name([[DeepSouthCon 58]] / [[ConGregate 2020]]) is in con.Override
            # which is only filled in for these complicated thingies.  Since they are on the same date, they sort together and this test ignores ones after the first.
            # TODO: What if there's another con on that date and it winds up sorted in between?
            if con.Text == lastcon.Text and con.DateRange == lastcon.DateRange:
                continue

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
                    f.write(" ||")

            # Format the convention name and location for tabular output
            nameText=con.LinkedName
            if con.Cancelled:
                nameText=f"<s>{nameText}</s>"

            if con.Virtual:
                nameText=f"''{nameText} (virtual)''"
            else:
                if len(con.LocalePage.Link) > 0:
                    nameText+=f"&nbsp;&nbsp;&nbsp;<small>({StripWikiBrackets(con.LocalePage.Link)})</small>"
            f.write(nameText+"\n")

            lastcon=con


        f.write("</tab>\n")
        f.write("{{conrunning}}\n[[Category:List]]\n")


    #..................................................
    # Generate a list of forthcoming and recent conventions:
    # All cons dated the day the report is generated (including two of a series if they are both announced)
    # If we have no instance of a con going forward, then go back as far as 2021 (skipping pure-virtual cons) and keep only the most recent
    # First, get rid of anything prior to 2022.
    recentCons=[x for x in conventionsByDate if x.DateRange.StartDate > FanzineDate(Year=2021, Month=12, Day=31)]

    # Now a list of all cons still in the future
    futureCons=[x for x in recentCons if x.DateRange.EndDate > FanzineDate(DateTime=datetime.now())]
    # And all cons in the 1/1/2022 to now period
    pastCons=[x for x in recentCons if x.DateRange.StartDate < FanzineDate(DateTime=datetime.now())]

    # Remove conventions from the pastCons list if the series is  reprepresented in the futureCons list
    futureSeriesNames=set([x.SeriesName for x in futureCons])
    pastCons=[x for x in pastCons if x.SeriesName not in futureSeriesNames]

    # Keep only the latest convention in a series in the pastCons list
    latestPastCons: dict[str, ConInstanceInfo]={}
    for con in pastCons:
        if con.SeriesName in latestPastCons.keys():     # Keep only the most recent past con
            if con.DateRange.StartDate < latestPastCons[con.SeriesName].DateRange.StartDate:
                continue
        latestPastCons[con.SeriesName]=con
    # And combine it all into a single list of relevant recent cons sorted by name
    currentCons=futureCons+[x for x in latestPastCons.values()]
    currentCons.sort(key=lambda x: x.DateRange)

    Log("Writing: Current Conventions (Fancy).txt", timestamp=True)
    with open("Current Conventions (Fancy).txt", "w+", encoding='utf-8') as f:
        f.write("This is a list of current SF conventions automatically extracted from Fancyclopedia 3\n\n")
        f.write("If a convention is missing from the list, it may have been added only recently, (this list was generated ")
        f.write(datetime.now().strftime("%A %B %d, %Y  %I:%M:%S %p")+" EST)")
        f.write(" or because we do not yet have information on the convention or because the convention's listing in Fancy 3 is a bit odd ")
        f.write("and the program which creates this list isn't parsing it.  In any case, we welcome help making it more complete!  Send corrections and updates to webmaster@fancyclopedia.org\n\n")
        f.write(f"The list currently has {len(currentCons)} conventions.\n")

        currentLetter=None
        # We're going to write a Fancy 3 wiki table
        # Two columns: Daterange and convention name and location
        # The date is not repeated when it is the same
        # The con name and location is crossed out when it was cancelled or moved and (virtual) is added when it was virtual
        f.write("<tab>\n")
        for con in currentCons:

            # Format the convention name and location for tabular output
            nameText=con.LinkedName
            if con.Cancelled:
                nameText=f"<s>{nameText}</s>"
            if con.Virtual:
                nameText=f"''{nameText} (virtual)''"

            seriesText=""
            # We want to add series info to conventions where the series is not in the convention name (e.g., Eastercons)
            # The series name may have differener capitaization (ignore) and may have some sort of designator in parens at the end (eg., Unicon (MD)).  Ignore that.
            sn=con.SeriesName.lower()
            sn=re.sub("\(.*\)\s*$", "", sn)
            if sn not in nameText.lower() and sn != "onesie conventions":
                seriesText=f"&nbsp;([[{con.SeriesName}]])"

            dateText=str(con.DateRange)
            if con.Cancelled:
                dateText=f"<s>{dateText}</s>"

            localeText=""
            if not con.Virtual:
                if len(con.LocalePage.Link) > 0:
                    localeText=StripWikiBrackets(con.LocalePage.Link)

            f.write(f"{nameText}{seriesText}&nbsp;&nbsp;&nbsp;{dateText}&nbsp;&nbsp;&nbsp;{localeText}\n")

        f.write("</tab>\n")
        f.write("{{conrunning}}\n[[Category:List]]\n")


    # ...
    # OK, now we have a dictionary of all the pages on Fancy 3, which contains all of their outgoing links
    # Build up a dictionary of redirects.  It is indexed by the canonical name of a page and the value is the canonical name of the ultimate redirect
    # Build up an inverse list of all the pages that redirect *to* a given page, also indexed by the page's canonical name. The value here is a list of canonical names.
    Log("***Create inverse redirects tables", timestamp=True)
    redirects: dict[str, str]={}            # Key is the name of a redirect; value is the ultimate destination
    inverseRedirects:dict[str, list[str]]=defaultdict(list)     # Key is the name of a destination page, value is a list of names of pages that redirect to it
    for fancyPage in fancyPagesDictByWikiname.values():
        if fancyPage.Redirect != "":
            redirects[fancyPage.Name]=fancyPage.Redirect
            inverseRedirects[fancyPage.Redirect].append(fancyPage.Name)
            if fancyPage.Redirect != fancyPage.Redirect:
                inverseRedirects[fancyPage.Redirect].append(fancyPage.Name)

    # Analyze the Locales
    # Create a list of things that redirect to a LocalePage, but are not tagged as a locale.
    Log("***Look for things that redirect to a LocalePage, but are not tagged as a Locale", timestamp=True)
    with open("Untagged locales.txt", "w+", encoding='utf-8') as f:
        for fancyPage in fancyPagesDictByWikiname.values():
            if fancyPage.IsLocale:                        # We only care about locales
                if fancyPage.Redirect == "":        # We don't care about redirects
                    if fancyPage.Name in inverseRedirects.keys():
                        for inverse in inverseRedirects[fancyPage.Name]:    # Look at everything that redirects to this
                            if not fancyPagesDictByWikiname[inverse].IsLocale:
                                if "-" not in inverse:                  # If there's a hyphen, it's probably a Wikidot redirect
                                    if inverse[1:] != inverse[1:].lower() and " " in inverse:   # There's a capital letter after the 1st and also a space
                                        f.write(f"{fancyPage.Name} is pointed to by {inverse} which is not a LocalePage\n")


    ###################################################
    # Now we have a dictionary of all the pages on Fancy 3, which contains all of their outgoing links
    # Build up an inverse list of all the pages that redirect *to* a given page, also indexed by the page's canonical name. The value here is a list of canonical names.
    inverseRedirects: dict[str, list[str]]=defaultdict(list)     # Key is the name of a destination page, value is a list of names of pages that redirect to it
    for fancyPage in fancyPagesDictByWikiname.values():
        if fancyPage.Redirect != "":
            inverseRedirects[fancyPage.Redirect].append(fancyPage.Name)

    # Create a dictionary of page references for people pages.
    # The key is a page's canonical name; the value is a list of pages at which they are referenced.
    peopleReferences: dict[str, list[str]]={}
    Log("***Creating dict of people references", timestamp=True)
    for fancyPage in fancyPagesDictByWikiname.values():
        if fancyPage.IsPerson:
            peopleReferences[fancyPage.Name]=[]
    for fancyPage in fancyPagesDictByWikiname.values():
        for outRef in fancyPage.OutgoingReferences:
            if outRef.LinkWikiName in peopleReferences.keys():
                peopleReferences[outRef.LinkWikiName].append(fancyPage.Name)

    Log("***Writing reports", timestamp=True)
    # Write out a file containing canonical names, each with a list of pages which refer to it.
    # The format will be
    #     **<canonical name>
    #       <referring page>
    #       <referring page>
    #     ...
    #     **<canonical name>
    #     ...
    Log("Writing: Referring pages for People.txt", timestamp=True)
    with open("Referring pages for People.txt", "w+", encoding='utf-8') as f:
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
    Log("Writing: Redirects.txt", timestamp=True)
    with open("Redirects.txt", "w+", encoding='utf-8') as f:
        for redirect, pages in inverseRedirects.items():
            f.write(f"**{redirect}\n")
            for page in pages:
                f.write(f"      ⭦ {page}\n")

    # Next, a list of redirects with a missing target
    Log("Writing: Redirects with missing target.txt", timestamp=True)
    allFancy3Pagenames=set([WindowsFilenameToWikiPagename(n) for n in allFancy3PagesFnames])
    with open("Redirects with missing target 2.txt", "w+", encoding='utf-8') as f:
        for fancyPage in fancyPagesDictByWikiname.values():
            dest=fancyPage.Redirect
            if dest != "" and dest not in allFancy3Pagenames:
                f.write(f"{fancyPage.Name} --> {dest}\n")


    # List pages which are not referred to anywhere and which are not Wikidot redirects
    Log("Writing: Wikidot redirects with no Mediawiki equivalent.txt", timestamp=True)
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
    Log("Writing: Pages never referred to.txt", timestamp=True)
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


    Log("Writing: Peoples rejected names.txt", timestamp=True)
    peopleNames: list[str]=[]
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
    Log("Writing: Peoples names.txt", timestamp=True)
    with open("Peoples names.txt", "w+", encoding='utf-8') as f:
        peopleNames.sort(key=lambda p: p.split()[-1][0].upper()+p.split()[-1][1:]+","+" ".join(p.split()[0:-1]))    # Invert so that last name is first and make initial letter UC.
        for name in peopleNames:
            f.write(name+"\n")

    # Create and write out a file of preferred forms of peoples' names
    # Each line is of the form
    #   <redirected page. -> <people page>
    # A people page is a page tagged as a person which is not a redirect
    Log("Writing: Peoples Canonical Names.txt", timestamp=True)
    with open("People Canonical Names.txt", "w+", encoding='utf-8') as f:
        for fancyPage in fancyPagesDictByWikiname.values():
            if fancyPage.IsRedirectpage:    # If a redirect page
                if not fancyPage.IsWikidot:  # Which is not a remnant Wikidot redirect page
                    redirect=fancyPage.Redirect
                    if redirect in fancyPagesDictByWikiname:    # Points to a page that exists
                        redirectPage=fancyPagesDictByWikiname[redirect]
                        redirectPage=fancyPagesDictByWikiname[redirect]
                        if redirectPage.IsPerson:   # Which is a person page or...
                            if fancyPage.IsPerson or not \
                                (fancyPage.IsAPA or fancyPage.IsLocale or fancyPage.IsClub or fancyPage.IsFanzine or fancyPage.IsPublisher or fancyPage.IsStore or
                                 fancyPage.IsConrunning or fancyPage.IsConInstance or fancyPage.IsCatchphrase or fancyPage.IsFiction or fancyPage.IsBook):
                                # ...is not some other kind of page (sometimes something like a one-person store is documented by a redirect to the owner's page, and we don't
                                # want those redirects to be alternate names of the owner
                                    f.write(f"{RemoveTrailingParens(fancyPage.Name)} --> {RemoveTrailingParens(RemoveTrailingParens(redirectPage.Name))}\n")


    # Create some reports on tags/Categories
    adminTags={"Admin", "mlo", "jrb", "Nofiles", "Nodates", "Nostart", "Noseries", "Noend", "Nowebsite", "Hasfiles", "Haslink", "Haswebsite", "Fixme", "Details", "Redirect", "Wikidot", "Multiple",
               "Choice", "Iframe", "Active", "Inactive", "IA", "Map", "Mapped", "Nocountry", "Noend", "Validated"}
    countryTags={"US", "UK", "Australia", "Ireland", "Europe", "Asia", "Canada"}
    ignoredTags=adminTags.copy()
    ignoredTags.union({"Fancy1", "Fancy2"})

    def ComputeTagCounts(pageDict: dict[str, F3Page], ignoredTags: set) -> tuple[dict[str, int], dict[str, int]]:
        tagcounts: dict[str, int]=defaultdict(int)
        tagsetcounts: dict[str, int]=defaultdict(int)
        for fp in pageDict.values():
            if not fp.IsRedirectpage:
                tagset=TagSet()
                tags=fp.Tags
                if len(tags) > 0:
                    for tag in tags:
                        if tag not in ignoredTags:
                            tagset.add(tag)
                        tagcounts[tag]+=1
                    tagsetcounts[str(tagset)]+=1
                else:
                    tagsetcounts["notags"]+=1
        return tagcounts, tagsetcounts

    tagcounts, tagsetcounts=ComputeTagCounts(fancyPagesDictByWikiname, ignoredTags)

    Log("Writing: Counts for individual tags.txt", timestamp=True)
    with open("Tag counts.txt", "w+", encoding='utf-8') as f:
        tagcountslist=[(key, val) for key, val in tagcounts.items()]
        tagcountslist.sort(key=lambda elem: elem[1], reverse=True)
        for tag, count in tagcountslist:
            f.write(f"{tag}: {count}\n")

    Log("Writing: Counts for tagsets.txt", timestamp=True)
    with open("Tagset counts.txt", "w+", encoding='utf-8') as f:
        tagsetcountslist=[(key, val) for key, val in tagsetcounts.items()]
        tagsetcountslist.sort(key=lambda elem: elem[1], reverse=True)
        for tagset, count in tagsetcountslist:
            f.write(f"{tagset}: {count}\n")

    ##################
    # Now redo the counts, ignoring countries
    ignoredTags=adminTags.copy().union(countryTags)
    tagcounts, tagsetcounts=ComputeTagCounts(fancyPagesDictByWikiname, ignoredTags)

    Log("Writing: Counts for tagsets without country.txt", timestamp=True)
    with open("Tagset counts without country.txt", "w+", encoding='utf-8') as f:
        for tagset, count in tagsetcounts.items():
            f.write(f"{tagset}: {count}\n")


    ##################
    # Now do it again, but this time look at all subsets of the tags (again, ignoring the admin tags)
    tagsetcounts: dict[str, int]=defaultdict(int)
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
                tagsetcounts[str(ts)]+=1

    Log("Writing: Counts for tagpowersets.txt", timestamp=True)
    with open("Tagpowerset counts.txt", "w+", encoding='utf-8') as f:
        for tagset, count in tagsetcounts.items():
            f.write(f"{tagset}: {count}\n")

    ##############
    # We want apazine and clubzine to be used in addition to fanzine.  Make a list of
    # First make a list of all the pages labelled as "fan" or "pro"
    Log("Writing: Apazines and clubzines that aren't fanzines.txt", timestamp=True)
    with open("Apazines and clubzines that aren't fanzines.txt", "w+", encoding='utf-8') as f:
        for fancyPage in fancyPagesDictByWikiname.values():
            # Then all the redirects to one of those pages.
            if ("Apazine" in fancyPage.Tags or "Clubzine" in fancyPage.Tags) and "Fanzine" not in fancyPage.Tags:
                f.write(fancyPage.Name+"\n")


    ##################
    # Make a list of all all-upper-case pages which are not tagged initialism.
    Log("Writing: Uppercase names which aren't marked as Initialisms.txt", timestamp=True)
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
                ignorelist: list[str]=["DSC", "CAN*CON", "ICFA", "NJAC", "OASIS", "OVFF", "URCON", "VCON"]
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
    Log("Writing: Tagging oddities.txt", timestamp=True)

    def WriteSelectedTags(fancyPagesDictByWikiname: dict[str, F3Page], select, f):
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
    Log("Writing: Mundanes.txt", timestamp=True)
    with open("Mundanes.txt", "w+", encoding='utf-8') as f:
        for fancyPage in fancyPagesDictByWikiname.values():
            # Then all the redirects to one of those pages.
            if fancyPage.IsMundane:
                f.write(f"{fancyPage.Name}: {fancyPage.Tags}\n")

    ##################
    # Compute some special statistics to display at fanac.org
    Log(f"Writing: Statistics.txt", timestamp=True)
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

