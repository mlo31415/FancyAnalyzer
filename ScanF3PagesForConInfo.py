from typing import Optional
import json
import re

from Log import Log, LogSetHeader
from HelpersPackage import CompressWhitespace, ConvertHTMLishCharacters
from HelpersPackage import WikiExtractLink, CrosscheckListElement, ScanForBracketedText

from ConInstanceInfo import ConInstanceInfo, ConInstanceLink
from FanzineIssueSpecPackage import FanzineDateRange
from LocalePage import LocaleHandling, LocalePage


###########
# Read through all F3Pages and build up a structure of conventions
# We do this by first looking at all conseries pages and extracting the info from their convention tables.
# (Later we'll get more info by reading the individual con pages.)

# Note: There are three convention entities
#       The con series (e.g., Boskone, Westercon)
#       The convention (e.g., Boskone 23, Westercon 18)
#       IndexTableEntry: Something to handle the fact that some conventions are members of two or more conseries and some conventions
#           have been scheduled, moved and cancelled.
def ScanF3PagesForConInfo(conventions, fancyPagesDictByWikiname):
    for page in fancyPagesDictByWikiname.values():

        # First, see if this is a Conseries page
        if not page.IsConSeries:
            Log("Not a Conseries: "+page.Name)
            continue

        Log("Processing "+page.Name)
        i=0
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
                if len(row) < numcolumns or len(row[conColumn]) == 0 or len(row[dateColumn]) == 0:
                    continue

                # Check the row for (virtual) in any form. If found, set the virtual flag and remove the text from the line
                virtual=False
                for idx, col in enumerate(row):
                    v2, col=ScanForVirtual(col)
                    if v2:
                        row[idx]=col  # Update row with the virtual flag removed
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

                # ............................
                # First the date column
                datetext=row[dateColumn]

                # For the dates column, we want to remove the virtual designation as it will just confuse later processing.
                # We want to handle the case where (virtual) is in parens, but also when it isn't.
                # We need two patterns here because Python's regex doesn't have balancing groups and we don't want to match unbalanced parens

                # Ignore anything in trailing parenthesis. (e.g, "(Easter weekend)", "(Memorial Day)")
                datetext=re.sub("\(.*\)\s?$", "", datetext)  # Note that this is greedy. Is that the correct things to do?
                # Convert the HTML characters some people have inserted into their ascii equivalents
                datetext=CompressWhitespace(datetext)
                # Remove leading and trailing spaces
                datetext=datetext.strip()

                # Now look for dates. There are many cases to consider:
                # 1: date                    A simple date (note that there will never be two simple dates in a dates cell)
                # 2: <s>date</s>             A canceled con's date
                # 3: <s>date</s> date        A rescheduled con's date
                # 4: <s>date</s> <s>date</s> A rescheduled and then cancelled con's dates
                # 5: <s>date</s> <s>date</s> date    A twice-rescheduled con's dates
                # m=re.match("^(:?(<s>.+?</s>)\s*)*(.*)$", datetext)
                pat="<s>.+?</s>"
                ds=re.findall(pat, datetext)
                if len(ds) > 0:
                    datetext=re.sub(pat, "", datetext).strip()
                if len(datetext) > 0:
                    ds.append(datetext)
                if len(ds) == 0:
                    Log("Date error: "+datetext)
                    continue

                # We have N groups up to N-1 of which might be None
                dates: list[FanzineDateRange]=[]
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

                # ............................................
                # Now handle the names column
                # Get the corresponding convention name(s).
                nameText=row[conColumn]
                # Clean up the text
                # Convert the HTML characters some people have inserted into their ascii equivalents
                nameText=ConvertHTMLishCharacters(nameText)
                # And get rid of hard line breaks
                nameText=nameText.replace("<br>", " ")
                # In some pages we italicize or bold the con's name, so remove spans of single quotes of length 2 or longer
                nameText=re.sub("'{2,}", "", nameText)

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
                def SplitWikiNametext(constr: str) -> tuple[str, str]:
                    # Now convert all link|text to separate link and text
                    # Do this for s1 and s2
                    m=re.match("\[\[(.+)\|(.+)]]$", constr)  # Split [[xxx|yyy]] into xxx and yyy
                    if m is not None:
                        return m.groups()[0], m.groups()[1]
                    m=re.match("\[\[(.+)]]$", constr)  # Look for a simple [[text]] page reference
                    if m is not None:
                        return "", m.groups()[0]
                    return "", constr

                # ----------------------------------------------------------
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
                        # If there's a colon, return the stuff before the colon
                        if ":" in name:
                            return name.split(":")[0].strip()
                        return name

                    # We want to take the leading con name
                    # There can be at most one con name which isn't cancelled, and it should be at the end, so first look for a <s>...</s> bracketed con names, if any
                    pat="^<s>(.*?)</s>"  # Note that .*? is non-greedy
                    m=re.match(pat, connamestr)
                    if m is not None:
                        s=m.groups()[0]
                        connamestr=re.sub(pat, "", connamestr).strip()  # Remove the matched part and trim whitespace
                        s=DeColonize(s)
                        l, t=SplitWikiNametext(s)
                        con=ConInstanceLink(Text=t, Link=l, Cancelled=True)
                        return con, connamestr

                    # OK, there are no <s>...</s> con names left.  So what is left might be [[name]] or [[link|name]]
                    pat="^(\[\[.*?]])"  # Anchored; '[['; non-greedy string of characters; ']]'
                    m=re.match(pat, connamestr)
                    if m is not None:
                        s=m.groups()[0]  # Get the patched part
                        connamestr=re.sub(pat, "", connamestr).strip()  # And remove it from the string and trim whitespace
                        s=DeColonize(s)
                        l, t=SplitWikiNametext(s)  # If text contains a "|" split it on the "|"
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
                seriesTableRowConEntries: list[ConInstanceLink|list[ConInstanceLink]]=[]

                # Do we have "/" in the con name that is not part of a </s> and not part of a fraction? If so, we have alternate names, not separate cons
                # The strategy here is to recognize the '/' which are *not* con name separators and turn them into '&&&', then split on the remaining '/' and restore the real ones
                def replacer(matchObject) -> str:  # This generates the replacement text when used in a re.sub() call
                    if matchObject.group(1) is not None and matchObject.group(2) is not None:
                        return matchObject.group(1)+"&&&"+matchObject.group(2)

                contextforsplitting=re.sub("(<)/([A-Za-z])", replacer, nameText)  # Hide the '/' in html items like </xxx>
                contextforsplitting=re.sub("([0-9])/([0-9])", replacer, contextforsplitting)  # Hide the '/' in fractions such as 1/2
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
                    alts.sort()  # Sort the list so that when this list is created from two or more different convention index tables, it looks the same and dups can be removed.
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
                        loc=WikiExtractLink(row[locColumn])  # If there is linked text, get it; otherwise use everything
                        locale=LocaleHandling().ScanForLocale(loc, page.Name)
                        if len(locale) > 0:
                            conlocation=locale[0]

                # Now we have cons and dates and need to create the appropriate convention entries.
                if len(seriesTableRowConEntries) == 0 or len(dates) == 0:
                    Log("Scan abandoned: ncons="+str(len(seriesTableRowConEntries))+"  len(dates)="+str(len(dates)), isError=True, Print=False)
                    continue

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
                        ci=ConInstanceInfo(Link=links, Text=names, Locale=conlocation, DateRange=dt,
                                           Virtual=False if cancelled else virtual, Cancelled=dt.Cancelled, SeriesName=page.Name)
                        conventions.Append(ci)
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
                        dates[i].Cancelled=False  # We've xfered this to ConInstanceInfo and don't still want it here because it would print twice
                        v=False if cancelled else virtual
                        ci=ConInstanceInfo(Link=seriesTableRowConEntries[i].Link, Text=seriesTableRowConEntries[i].Text, Locale=conlocation, DateRange=dates[i], Virtual=v, Cancelled=cancelled,
                                           SeriesName=page.Name)
                        if ci.DateRange.IsEmpty():
                            Log(f"***{ci.Link} has an empty date range: {ci.DateRange}", isError=True)
                        Log(f"#append 2: {ci}", Print=False)
                        conventions.Append(ci)

                elif len(seriesTableRowConEntries) > 1 and len(dates) == 1:
                    # Log(f"Case 3: {len(seriesTableRowConEntries)=}")
                    # for i in range(len(seriesTableRowConEntries)):
                    #     Log(f"             {str(seriesTableRowConEntries[i])}")
                    # Log(f"         {len(dates)=}")
                    # Log(f"         {str(dates[0])=}")
                    # Multiple cons all with the same dates
                    for co in seriesTableRowConEntries:
                        cancelled=co.Cancelled or dates[0].Cancelled
                        dates[0].Cancelled=False
                        v=False if cancelled else virtual
                        ci=ConInstanceInfo(Link=co.Link, Text=co.Text, Locale=conlocation, DateRange=dates[0], Virtual=v, Cancelled=cancelled, SeriesName=page.Name)
                        conventions.Append(ci)
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
                        dt.Cancelled=False
                        v=False if cancelled else virtual
                        ci=ConInstanceInfo(Link=seriesTableRowConEntries[0].Link, Text=seriesTableRowConEntries[0].Text, Locale=conlocation, DateRange=dt, Virtual=v, Cancelled=cancelled,
                                           SeriesName=page.Name)
                        conventions.Append(ci.Unwind())
                        Log(f"#append 4: {ci}", Print=False)

                else:
                    # We really should deal with the case of Westercon 75/Loscon 49... What an ugly mess!
                    Log(f"Shouldn't happen! ncons={len(seriesTableRowConEntries)}  {len(dates)=}", isError=True)


#---------------------------------------------------------------------------
# Scan for a virtual flag
# Return True/False and the remaining text after the V-flag is removed
def ScanForVirtual(s: str) -> tuple[bool, str]:
    pattern = "\((:?virtual|online|held online|moved online|virtual convention)\)"

    # First look for one of the alternatives (contained in parens) *anywhere* in the text
    newval = re.sub(pattern, "", s, flags=re.IGNORECASE)  # Check w/parens 1st so that if parens exist, they get removed.
    if s != newval:
        return True, newval.strip()

    # Now look for alternatives by themselves.  So we don't pick up junk, we require that the non-parenthesized alternatives be alone in the cell
    newval = re.sub("\s*" + pattern + "\s*$", "", s, flags=re.IGNORECASE)       #TODO: Is this patteren anchored to the start of the text? Shoudl it be?
    if s != newval:
        return True, newval.strip()

    return False, s
