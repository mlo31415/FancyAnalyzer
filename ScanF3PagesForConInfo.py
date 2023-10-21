import re

from Log import Log, LogSetHeader, LogError
from HelpersPackage import CompressWhitespace, ConvertHTMLishCharacters, RemoveTopBracketedText, FindAnyBracketedText
from HelpersPackage import CrosscheckListElement, ScanForBracketedText

from FanzineIssueSpecPackage import FanzineDateRange
from LocalePage import LocaleHandling
from Conventions import Conventions, IndexTableSingleNameEntry, IndexTableNameEntry, ConInstanceInfo


###########
# Read through all F3Pages and build up a structure of conventions
# We do this by first looking at all conseries pages and extracting the info from their convention tables.
# (Later we'll get more info by reading the individual con pages.)

# Note: There are three convention entities
#       The con series (e.g., Boskone, Westercon)
#       The convention (e.g., Boskone 23, Westercon 18)
#       IndexTableEntry: Something to handle the fact that some conventions are members of two or more conseries and some conventions
#           have been scheduled, moved and cancelled.
def ScanF3PagesForConInfo(fancyPagesDictByWikiname) -> Conventions:

    # Build a list of Con series pages.  We'll use this later to check links when analyzing con index table entries
    conseries: list[str]=[page.Name for page in fancyPagesDictByWikiname.values() if page.IsConSeries]

    # Build the main list of conventions by walking the convention index table on each of the conseries pages
    conventions: Conventions=Conventions()
    for page in fancyPagesDictByWikiname.values():
        if not page.IsConSeries:    # We could use conseries for this, but it would not be much faster and would result in an extra layer of indent.
            continue

        Log("Processing conseries: "+page.Name)

        # Sometimes there will be multiple tables in a con series index page. It's hard to tell which is for what, so we check each of them.
        for index, table in enumerate(page.Tables):
            numcolumns=len(table.Headers)

            # We require that we have convention and date columns, though we allow alternative column names
            conColumn=CrosscheckListElement(["Convention", "Convention Name", "Name"], table.Headers)
            if conColumn is None:
                Log(f"***Can't find Convention column in table {index+1} of {len(page.Tables)} on page {page.Name}", isError=True, Print=False)
                continue

            dateColumn=CrosscheckListElement(["Date", "Dates"], table.Headers)
            if dateColumn is None:
                Log(f"***Can't find dates column in table {index+1} of {len(page.Tables)} on page {page.Name}", isError=True, Print=False)
                continue

            # We don't log a missing location column because that is common and not an error -- if we don't find one here,
            # we'll try to get the location later by analyzing the con instance's page
            locColumn=CrosscheckListElement(["Locations", "Location"], table.Headers)

            # Finally, make sure the table has rows
            if table.Rows is None:
                Log(f"***Table {index+1} of {len(page.Tables)} on page {page.Name} looks like a convention table, but has no rows", isError=True, Print=False)
                continue

            # We have a convention table with the required minimum structure.  Walk it, extracting the individual conventions
            for row in table.Rows:
                LogSetHeader(f"Processing: {page.Name}  row: {row}")
                # Skip rows with merged columns, and also rows where either the date cell or the convention name cell is empty
                if len(row) < numcolumns or len(row[conColumn]) == 0 or len(row[dateColumn]) == 0:
                    continue

                # Check the row for (virtual) in any of several form. If found, set the virtual flag and remove the text from the line
                virtual=False
                # Check each column in turn.  (It would be better if we had a standard. Oh, well.)
                for idx, cell in enumerate(row):
                    v2, col=ScanForVirtual(cell)
                    if v2:
                        row[idx]=cell  # Update the cell with the virtual flag removed
                    virtual=virtual or v2
                Log(f"{virtual=}", Print=False)

                location=""
                if locColumn is not None:
                    location=row[locColumn].strip()

                # ............................................
                # Now handle the names and dates columns.  Get the corresponding convention name(s) and dates.
                nameEntryList=ExtractConNameInfo(row[conColumn], conseries)
                x=nameEntryList.DisplayNameMarkup
                dateEntryList=ExtractDateInfo(row[dateColumn], page.Name, row)

                # Now for the hard work of making sense of this...
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

                if len(nameEntryList) == 0:
                    Log(f"No names found in row: {row}")
                    continue

                if len(nameEntryList) == len(dateEntryList):
                    # Easy-peasy. N cons with N dates.  Either a boring con that was simplay held or onw which was renamed when it went to a new date.
                    for i in range(len(nameEntryList)):
                        nel=nameEntryList[i]
                        dtel=dateEntryList[i]
                        conventions.Append([ConInstanceInfo(Link=nel.Link, Text=nel.Text, DateRange=dtel, Locale=location, Virtual=nel.Virtual, Cancelled=nel.Cancelled or dtel.Cancelled)])
                    continue

                if len(dateEntryList) > 1 and len(nameEntryList) == 1:
                    # This is the case of a convention which was postponed and perhaps cancelled, but retained the same name.
                    for i in range(len(dateEntryList)):
                        nel=nameEntryList[0]
                        dtel=dateEntryList[i]
                        conventions.Append([ConInstanceInfo(Link=nel.Link, Text=nel.Text, DateRange=dtel, Locale=location, Virtual=nel.Virtual, Cancelled=nel.Cancelled or dtel.Cancelled)])
                    continue

                # The leftovers will be uncommon, but we still do need to handle them.
                LogError(f"ScanF3PagesForConInfo() Name/date combinations not yet handled: {page.Name}: {len(dateEntryList)=}  {len(nameEntryList)=}  {row=}")






    # The basic convention data has been mined from the convention series pages.
    # Now let's look through all the con instances and see if we can get more location information from them.
    # (Not all con series tables contain location information.)

    # Generate a report of cases where we have non-identical con information from both sources.
    Log("Writing: 'Con location discrepancies.txt'", timestamp=True)
    with open("Con location discrepancies.txt", "w+", encoding='utf-8') as f:
        for page in fancyPagesDictByWikiname.values():
            if not page.IsConInstance:
                continue

            # We have a con instance page

            # If the page has a Locale set, it overrides any internal data
            loc=LocaleHandling().LocaleFromName(page.LocaleStr)
            if not loc.IsEmpty:
                if page.Name not in conventions:
                    f.write(f"{page.Name} not in conventions\n")
                    continue
                for con in conventions[page.Name]:
                    con.LocalePage=loc        #TODO: We really ought to locate the specific con in the list
                Log(f" {page.Name=}  gets loc{{loc=}}", Flush=True)
                continue

            # If it doesn't have a Locale, we search through its text for something that looks like a placename.
            #TODO: Shouldn't we move this upwards and store the derived location in otherwise-empty page.Locales?
            locale=LocaleHandling().ScanConPageforLocale2(page.Source)
            if locale is not None:
                # Find the convention in the conventions dictionary and add the location if appropriate.
                if page.Name in conventions:
                    for con in conventions[page.Name]:
                        if not locale.LocMatch(con.LocalePage.PreferredName):
                            if con.LocalePage.IsEmpty:   # If there previously was no location from the con series page, substitute what we found in the con instance page
                                con.LocalePage=locale
                                continue
                            Log(f"{page.Name}: Location mismatch: '{locale.PreferredName}' != '{con.LocalePage.PreferredName}'\n")
                            f.write(f"{page.Name}: Location mismatch: '{locale.PreferredName}' != '{con.LocalePage.PreferredName}'\n")
                            f.flush()

    # All done, return the collected convention information
    return conventions


def ExtractDateInfo(datetext: str, name: str, row) -> list[FanzineDateRange]:

    Log(f"ExtractDateInfo({row})")

    # Ignore anything in trailing parenthesis. (e.g, "(Easter weekend)", "(Memorial Day)")
    datetext=re.sub("\(.*\)\s?$", "", datetext)  # TODO: Note that this is greedy. Is that the correct thing to do?
    # Convert the HTML whitespace characters some people have inserted into their ascii equivalents and then compress all spans of whitespace into a single space.
    # Remove leading and trailing spaces
    datetext=CompressWhitespace(datetext).strip()
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
    ds=[x for x in ds if x != ""]  # Remove empty matches
    if len(ds) == 0:
        Log(f"Date error: {datetext}")
        return []
    # Examine the dates in turn
    dates: list[FanzineDateRange]=[]
    for d in ds:
        c, s=ScanForBracketedText(d, "s")
        dr=FanzineDateRange().Match(s)
        dr.Cancelled=c
        if dr.Duration() > 7:
            Log(f"??? convention has long duration: {dr}", isError=True)
        if not dr.IsEmpty():
            dates.append(dr)
    if len(dates) == 0:
        Log(f"***No dates found - {name}:  {datetext=}  {row=}", isError=True)
    elif len(dates) == 1:
        Log(f"{name}  row: {row}: 1 date: {dates[0]}", Print=False)
    else:
        Log(f"{name}  row: {row}: {len(dates)} dates: {dates[0]}")
        for d in dates[1:]:
            Log(f"           {d}", Print=False)

    return dates

#
# def ExtractConNameInfo(nameText, conventions, dates, locColumn, page, row, virtual):
#
#     # Clean up the text
#     # Convert the HTML characters some people have inserted into their ascii equivalents
#     nameTextCleaned=ConvertHTMLishCharacters(nameText)
#     # And get rid of hard line breaks
#     nameTextCleaned=nameTextCleaned.replace("<br>", " ").strip()
#     # In some pages we italicize or bold the con's name, so remove spans of single quotes of length 2 or longer
#     nameTextCleaned=re.sub("'{2,}", "", nameTextCleaned)
#     # Create the display name for this entry.  To get it, we need to do some processing.
#     # We convert all links into plain text and items of the form [[xxx|yyy]] will be converted to yyy only.
#     # We also change all /s to be surrounded by exactly one space on each side.
#     # First, deal with annoying use of templates
#     displayName=nameTextCleaned
#     if "{{" in displayName:
#         displayName=re.sub("{{([^}]*?)\|(.*?)}}", r"\2", displayName)
#     if "|" in displayName:
#         # Replace the xxx|yyy with yyy
#         displayName=re.sub(r"\[\[([^\]]*?)\|([^\]]*?)]]", r"\2", displayName)
#     displayName=re.sub("(\[\[|]])", "", displayName)  # Delete pairs of square brackets
#     displayName=displayName.replace("/", " / ")
#     displayName=CompressWhitespace(displayName)
#     if nameTextCleaned.count("[[") != nameTextCleaned.count("]]"):
#         Log("'"+nameText+"' has unbalanced double brackets. This is unlikely to end well...", isError=True)
#     # An individual name is of one of these forms:
#     #   xxx
#     # [[xxx]] zzz               Ignore the "zzz"
#     # [[xxx|yyy]]               Use just xxx
#     # [[xxx|yyy]] zzz           Ignore the zzz
#     # An individual name can be cancelled:
#     # <s>name</s>
#     # A convention can have multiple actual alternative names of the form name1 / name2 / name 3
#     # These are two or three different names for the same con.
#     # A typical case is where a con is part of multiple series at once, e.g., a DeepSouthCon held with a local con
#     # Note the distinction between multiple cons and multiple names for the same con.  The "/" is the distinguishing mark
#     # When the name text has multiple con names that are not alternatives, they may match multiple dates in the date column, like when a
#     # a con converted from real to virtual while changing its name and keeping its dates:
#     # E.g., <s>[[FilKONtario 30]]</s> [[FilKONtari-NO]] (trailing stuff)
#     # Whatcon 20: This Year's Theme -- need to split on the colon and ignore the rest
#     # We will assume that there is only limited mixing of these forms!  E.g., a con with multiple names is either cancelled altogether or not cancelled.
#     # Create a list of convention names found along with any attached cancellation/virtual flags and date ranges
#     seriesTableRowConEntries: list[ConInstanceLink|list[ConInstanceLink]]=[]
#
#     # Do we have "/" in the con name that is not part of a </s> and not part of a fraction? If so, we have alternate names, not separate cons
#     # The strategy here is to recognize the '/' which are *not* con name separators and turn them into '&&&', then split on the remaining '/' and restore the real ones
#     def replacer(matchObject) -> str:  # This generates the replacement text when used in a re.sub() call
#         if matchObject.group(1) is not None and matchObject.group(2) is not None:
#             return matchObject.group(1)+"&&&"+matchObject.group(2)
#
#     contextforsplitting=re.sub("(<)/([A-Za-z])", replacer, nameTextCleaned)  # Hide the '/' in html items like </xxx>
#     contextforsplitting=re.sub("([0-9])/([0-9])", replacer, contextforsplitting)  # Hide the '/' in fractions such as 1/2
#     contextlist=contextforsplitting.split("/")  # Split on any remaining '/'s
#     contextlist=[x.replace("&&&", "/").strip() for x in contextlist]  # Restore the '/'s that had been hidden as &&& (and strip, just to be safe)
#     contextlist=[x for x in contextlist if len(x) > 0]  # Squeeze out any empty splits
#     if len(contextlist) > 1:
#         alts: list[ConInstanceLink]=[]
#         for con in contextlist:
#             c, _=NibbleConNametext(con)
#             if c is not None:
#                 alts.append(c)
#         alts.sort()  # Sort the list so that when this list is created from two or more different convention index tables, it looks the same and dups can be removed.
#         seriesTableRowConEntries.append(alts)
#     else:
#         # Ok, we have one or more names and they are for different cons
#         while len(nameTextCleaned) > 0:
#             con, nameTextCleaned=NibbleConNametext(nameTextCleaned)
#             if con is None:
#                 break
#             seriesTableRowConEntries.append(con)
#     # If the con series table has a location column, extract the text from that cell
#     conlocation: LocalePage=LocalePage()
#     if locColumn is not None:
#         if locColumn < len(row) and len(row[locColumn]) > 0:
#             loc=WikiExtractLink(row[locColumn])  # If there is linked text, get it; otherwise use everything
#             locale=LocaleHandling().ScanForLocale(loc, page.Name)
#             if len(locale) > 0:
#                 conlocation=locale[0]
#     # Now we have cons and dates and need to create the appropriate convention entries.
#     if len(seriesTableRowConEntries) == 0 or len(dates) == 0:
#         Log("Scan abandoned: ncons="+str(len(seriesTableRowConEntries))+"  len(dates)="+str(len(dates)), isError=True, Print=False)
#         i=0  # continue
#     # The first case we need to look at it whether cons[0] is a list
#     # This is one con with multiple names
#     if type(seriesTableRowConEntries[0]) is list:
#         # Log(f"Case 1: {len(seriesTableRowConEntries[0])=}")
#         # for i in range(len(seriesTableRowConEntries[0])):
#         #     Log(f"             {str(seriesTableRowConEntries[0][i])}")
#         # Log(f"         {len(dates)=}")
#         # Log(f"         {str(dates[0])=}")
#         # By definition there is only one element. Extract it.  There may be more than one date.
#         assert len(seriesTableRowConEntries) == 1 and len(seriesTableRowConEntries[0]) > 0
#         links=[]
#         names=[]
#         cancelled=False
#         for co in seriesTableRowConEntries[0]:
#             links.append(co.Link)
#             names.append(co.Text)
#             cancelled=cancelled or co.Cancelled
#
#         for dt in dates:
#             cancelled=cancelled or dt.Cancelled
#             ci=ConInstanceInfo(Link=links, Text=names, Locale=conlocation, DateRange=dt, DisplayName=displayName,
#                                Virtual=False if cancelled else virtual, Cancelled=dt.Cancelled, SeriesName=page.Name)
#             conventions.Append(ci)
#             Log(f"#append 1: {ci}", Print=False)
#
#     # OK, in all the other cases cons is a list[ConInstanceInfo]
#     # Check to see if the number of CILs is the same as the number of dates
#     elif len(seriesTableRowConEntries) == len(dates):
#         # Log(f"Case 2: {len(seriesTableRowConEntries)=}")
#         # for i in range(len(seriesTableRowConEntries)):
#         #     Log(f"             {str(seriesTableRowConEntries[i])}")
#         # Log(f"         {len(dates)=}")
#         # for i in range(len(dates)):
#         #     Log(f"             {str(dates[i])=}")
#         # Add each con with the corresponding date
#         for i in range(len(seriesTableRowConEntries)):
#             cancelled=seriesTableRowConEntries[i].Cancelled or dates[i].Cancelled
#             dates[i].Cancelled=False  # We've xfered this to ConInstanceInfo and don't still want it here because it would print twice
#             v=False if cancelled else virtual
#             ci=ConInstanceInfo(Link=seriesTableRowConEntries[i].Link, Text=seriesTableRowConEntries[i].Text, Locale=conlocation, DateRange=dates[i], Virtual=v, Cancelled=cancelled,
#                                SeriesName=page.Name)
#             if ci.DateRange.IsEmpty():
#                 Log(f"***{ci.Link} has an empty date range: {ci.DateRange}", isError=True)
#             Log(f"#append 2: {ci}", Print=False)
#             conventions.Append(ci)
#
#     # Multiple names, one date
#     elif len(seriesTableRowConEntries) > 1 and len(dates) == 1:
#         # Log(f"Case 3: {len(seriesTableRowConEntries)=}")
#         # for i in range(len(seriesTableRowConEntries)):
#         #     Log(f"             {str(seriesTableRowConEntries[i])}")
#         # Log(f"         {len(dates)=}")
#         # Log(f"         {str(dates[0])=}")
#         # Multiple cons all with the same dates
#         for co in seriesTableRowConEntries:
#             cancelled=co.Cancelled or dates[0].Cancelled
#             dates[0].Cancelled=False
#             v=False if cancelled else virtual
#             ci=ConInstanceInfo(Link=co.Link, Text=co.Text, Locale=conlocation, DateRange=dates[0], Virtual=v, Cancelled=cancelled, SeriesName=page.Name)
#             conventions.Append(ci)
#             Log(f"#append 3: {ci}", Print=False)
#
#     # Multiple dates, one name
#     elif len(seriesTableRowConEntries) == 1 and len(dates) > 1:
#         # Log(f"Case 4: {len(seriesTableRowConEntries[0])=}")
#         # for i in range(len(seriesTableRowConEntries[0])):
#         #     Log(f"             {str(seriesTableRowConEntries[0][i])}")
#         # Log(f"         {len(dates)=}")
#         # for i in range(len(dates)):
#         #     Log(f"             {str(dates[0][i])=}")
#         for dt in dates:
#             cancelled=seriesTableRowConEntries[0].Cancelled or dt.Cancelled
#             dt.Cancelled=False
#             v=False if cancelled else virtual
#             ci=ConInstanceInfo(Link=seriesTableRowConEntries[0].Link, Text=seriesTableRowConEntries[0].Text, Locale=conlocation, DateRange=dt, Virtual=v, Cancelled=cancelled,
#                                SeriesName=page.Name)
#             conventions.Append(ci.Unwind())
#             Log(f"#append 4: {ci}", Print=False)
#
#     # Oops.
#     # Probably multiple names and multiple dates, but not the same number.
#     else:
#         Log(f"{sum([x for x in range(1, 100)])=}")
#         i=0
#         # We really should deal with the case of Westercon 75/Loscon 49... What an ugly mess!
#         Log(f"{type(seriesTableRowConEntries)=}", Flush=True)
#         Log(f"{len(seriesTableRowConEntries)=}", Flush=True)
#         Log(f"Shouldn't happen! ncons={len(seriesTableRowConEntries)}  {len(dates)=}", isError=True)

# Examples:
# Single date thingies:
# [[Boskone 23]]
# [[DeepSouthCon 13]] / [[Rivercon I]]		        # Both link to same page
# [[DeepSouthCon 15|DeepSouthCon 15 / B'hamacon 1]] # Note slash inside [[]]
# [[DeepSouthCon 34]] / [[Beachcon]]		        # Both link to same page
# [[DeepSouthCon 62]] / ConToberFest
# <s>[[ABC-DSC|DeepSouthCon 54]] / [[ABC-DSC]]</s>

# Some multiple date thingies:
# <s>[[Westercon 73]]</s><br>/ [[Loscon 47]] || <s>July 2-5, 2020</s><br><s>July 1-4, 2021</s> <br>November 26-28, 2021
# <s>[[Westercon 75]]</s><br>/ [[Loscon 49]] || <s>June 30-July 3, 2023</s><br>{{nowrap|November 24–26, 2023}}
# [[Discon III]] || <s>August 25–29, 2021</s><br>December 15–19, 2021
# [[FilKONtario 2022]] (aka '''FK-nO 3''') (virtual)        # Note explanatory matter at end of name.  Gotta save that.

# The plan is first to strip garbage from the name (e.g., HTML (e.g., <br>) and templates {{}} and Wiki markup (e.g., ''') used for formatting).
# Merge spans of whitespace to a single space.
# Then decide if we have a slash inside the brackets or outside.  Slashs inside brackets are part of the name.  Slashs outside separate names.
# We assume that anything inside square brackets is a convention reference.



def ExtractConNameInfo(nameText: str, conseries: list[str]) -> IndexTableNameEntry:
    # The output is a list of IndexTableEntrys and the display name
    Log(f"ExtractConNameInfo2({nameText})")

    # Clean up the text
    # Convert the HTML characters some people have inserted into their ascii equivalents
    nameTextCleaned=ConvertHTMLishCharacters(nameText)
    # And get rid of hard line breaks
    nameTextCleaned=nameTextCleaned.replace("<br>", " ").strip()
    # In some pages we italicize or bold the con's name, so remove spans of single quotes of length 2 or longer
    nameTextCleaned=re.sub("'{2,}", "", nameTextCleaned)
    # Create the display name for this entry.  To get it, we need to do some processing.
    # We convert all links into plain text and items of the form [[xxx|yyy]] will be converted to yyy only.
    # We also change all /s to be surrounded by exactly one space on each side.

    # First, deal with annoying use of templates
    if "{{" in nameTextCleaned:
        nameTextCleaned=re.sub("{{([^}]*?)\|(.*?)}}", r"\2", nameTextCleaned)

    # Look for virtual or online and remove it if found
    # We are assuming that virtual conventions are not cancelled and replaced by some other convention.  E.g., (virtual) applies to the last con in a list.
    pat=r"\(?(virtual|online)\)?"
    m=re.search(pat, nameTextCleaned)
    virtual=False
    if m is not None:
        virtual=True
        nameTextCleaned=re.sub(pat, "", nameTextCleaned)

    # At this point we should have pretty well-cleaned info.  Here are the examples, from above as they would have been changed by this processing.
    # Also, removing the date info for now.
    # Examples:
    # Single date thingies:
    # [[Boskone 23]]
    # [[DeepSouthCon 13]] / [[Rivercon I]]		        # Both link to same page
    # [[DeepSouthCon 15|DeepSouthCon 15 / B'hamacon 1]] # Note slash inside [[]]
    # [[DeepSouthCon 34]] / [[Beachcon]]		        # Both link to same page
    # [[DeepSouthCon 62]] / ConToberFest
    # <s>[[ABC-DSC|DeepSouthCon 54]] / [[ABC-DSC]]</s>

    # Some multiple date thingies:
    # <s>[[Westercon 73]]</s> / [[Loscon 47]]
    # <s>[[Westercon 75]]</s> / [[Loscon 49]]
    # [[Discon III]]
    # [[FilKONtario 2022]] (aka FK-nO 3)         # Note explanatory matter at end of name.  Gotta save that.

    # Run through the name(s).
    # When names are separated by " / ", they are *alternative* names. When it's just a space or a comma, the con has been renamed.
    # # names=[x.strip() for x in nameTextCleaned.split("/")]
    #
    # # An individual name is of one of these forms:
    # #   xxx
    # # [[xxx]] zzz               Ignore the "zzz"
    # # [[xxx|yyy]]               Use just xxx
    # # [[xxx|yyy]] zzz           Ignore the zzz
    # # An individual name can be cancelled:
    # # <s>name</s>

    names=SplitByTopLevelSlashes(nameTextCleaned)

    # Now we have a list of /-separated distinct names.
    # Once again, from the list of examples, here are the names to be interpreted. (Redundancy removed.)
    # [[Boskone 23]]
    # [[DeepSouthCon 15|DeepSouthCon 15 / B'hamacon 1]]     # Note slash inside [[]]
    # [[DeepSouthCon 34]] / [[Beachcon]]		            # Both link to same page
    # [[DeepSouthCon 62]] / ConToberFest
    # <s>[[ABC-DSC|DeepSouthCon 54]] / [[ABC-DSC]]</s>
    # <s>[[Westercon 73]]</s>
    # [[FilKONtario 2022]] (aka FK-nO 3)            # Note explanatory matter at end of name.  Gotta save that.

    # Interpret each in turn and add them to the entry list.
    entryList=IndexTableNameEntry()
    for name1 in names:
        # Does this name have a strikeout indicating cancellation?  If so, note this and remove the strikeout.
        name1, c1=RemoveTopBracketedText(name1, "s")

        # It's now possible that we have one or more top-level slashes, e.g., [[ABC-DSC|DeepSouthCon 54]] / [[ABC-DSC]] now that the strike-outs have been removed
        # So do another level of slash-detection
        names1=SplitByTopLevelSlashes(name1)
        for name2 in names1:
            name2, c2=RemoveTopBracketedText(name2, "s")
            # Now we must have something of the form "abc <s>[[xxx|yyy]]</s> def" where any of the elements may be missing as long as at least one of the alphabetic elements exists
            if "<s>" in name2:      #Detect and remove any <s>
                lead2, _, content2, remainder2=FindAnyBracketedText(name2)
                c2=True
                name2=lead2+" "+content2+" "+remainder2
            # Now we have "abc [[xxx|yyy]] def".  Parse it.
            m=re.match(r"^(.*?)\[\[(.*?)\]\](.*)$", name2)
            if m is not None:
                lead2=m.groups()[0]
                text2=link2=m.groups()[1]
                remainder2=m.groups()[2]
            else:
                lead2=name2
                text2=link2=""
                remainder2=""

            # Can we split content2 into a list+text?
            if "|" in text2:
                link2, text2=text2.split("|")

            # Let's add this to the list
            cancelled=c2 or c2
            v=virtual and not cancelled     # When a con can't run live it is either cancelled or run virtually.
            # Suppress links to conseries pages
            if link2 in conseries:
                link2=""
            entryList.Append(IndexTableSingleNameEntry(Link=link2, Text=text2, Lead=lead2, Remainder=remainder2, Cancelled=cancelled, Virtual=v))

    return entryList



def SplitByTopLevelSlashes(nameTextCleaned) -> list[str]:
    # First, split the text into pieces by "/" *outside* of square brackets
    listofslashlocs=[-1]        # Starting point for the first range if there is one.
    depth=0
    for i in range(len(nameTextCleaned)):
        if nameTextCleaned[i] == "[":
            depth+=1
        elif nameTextCleaned[i] == "]":
            depth-=1
        elif nameTextCleaned[i] == "/" and depth == 0:
            listofslashlocs.append(i)
    names: list[str]=[]
    if len(listofslashlocs) == 1:
        names=[nameTextCleaned]  # If no top-level slashes were found, we have a list of one name
    else:
        listofslashlocs.append(len(nameTextCleaned))    # This gives us the ending index for the last piece.
        for i in range(len(listofslashlocs)-1):
            names.append(nameTextCleaned[listofslashlocs[i]+1:listofslashlocs[i+1]])

    return names


# def hold(names):
#     entryList: list[IndexTableSingleEntry]=[]
#     for name in names:
#         n=""
#         l=""
#         name, c=FindAndReplaceBracketedText(name, "s", "")
#
#         # Now all we have -- or should have -- is a standard Mediawiki link
#         if "|" in name:     # We have something of the form [[xxx|ttt]]
#             m=re.match(r"\[\[([^\]]*?)\|([^\]]*?)]]", name)
#             if m is None:
#                 LogError(f"ExtractConNameInfo2('{nameText}' '|' found, but no match of '{name}'")
#                 continue
#             n=m.groups()[0]
#             l=m.groups()[1]
#         elif "[[" in name:      # Is it [[tttt]]?
#             m=re.match(r"\[\[([^\]]*?[^\]]*?)]]", name)
#             if m is None:
#                 LogError(f"ExtractConNameInfo2('{nameText}' '[[' found, but no match of '{name}'")
#                 continue
#             n=l=m.groups()[0]
#         else:       # is it just ttt (no brackets)?
#             n=l=name
#
#         entryList.append(IndexTableSingleEntry(Text=n, Link=l, Cancelled=c, Virtual=v))
#
#     return entryList, nameTextCleaned


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


# # Take a Wikidot page reference and extract its text and link (if different)
# # Return them as (link, text)
# def SplitWikiNametext(constr: str) -> tuple[str, str]:
#     # Now convert all link|text to separate link and text
#     # Do this for s1 and s2
#     m=re.match("\[\[(.+)\|(.+)]]$", constr)  # Split [[xxx|yyy]] into xxx and yyy
#     if m is not None:
#         return m.groups()[0], m.groups()[1]
#     m=re.match("\[\[(.+)]]$", constr)  # Look for a simple [[text]] page reference
#     if m is not None:
#         return "", m.groups()[0]
#     return "", constr


# # ----------------------------------------------------------
# # We assume that the cancelled con names precede the uncancelled ones
# # On each call, we find the first con name and return it (as a ConName) and the remaining text as a tuple
# def NibbleConNametext(connamestr: str) -> tuple[Optional[ConInstanceLink], str]:
#     connamestr=connamestr.strip()
#     if len(connamestr) == 0:
#         return None, connamestr
#
#     # Change 'name: stuff' into just 'name'
#     def DeColonize(name: str) -> str:
#         if len(name) == 0:
#             return ""
#         # If there's a colon, return the stuff before the colon
#         if ":" in name:
#             return name.split(":")[0].strip()
#         return name
#
#     # We want to take the leading con name
#     # There can be at most one con name which isn't cancelled, and it should be at the end, so first look for a <s>...</s> bracketed con names, if any
#     pat="^<s>(.*?)</s>"  # Note that .*? is non-greedy
#     m=re.match(pat, connamestr)
#     if m is not None:
#         s=m.groups()[0]
#         connamestr=re.sub(pat, "", connamestr).strip()  # Remove the matched part and trim whitespace
#         s=DeColonize(s)
#         l, t=SplitWikiNametext(s)
#         con=ConInstanceLink(Text=t, Link=l, Cancelled=True)
#         return con, connamestr
#
#     # OK, there are no <s>...</s> con names left.  So what is left might be [[name]] or [[link|name]]
#     pat="^(\[\[.*?]])"  # Anchored; '[['; non-greedy string of characters; ']]'
#     m=re.match(pat, connamestr)
#     if m is not None:
#         s=m.groups()[0]  # Get the patched part
#         connamestr=re.sub(pat, "", connamestr).strip()  # And remove it from the string and trim whitespace
#         s=DeColonize(s)
#         l, t=SplitWikiNametext(s)  # If text contains a "|" split it on the "|"
#         con=ConInstanceLink(Text=t, Link=l, Cancelled=False)
#         return con, connamestr
#
#     # So far we've found nothing
#     if len(connamestr) > 0:
#         connamestr=DeColonize(connamestr)
#         if len(connamestr) == 0:
#             return None, ""
#         con=ConInstanceLink(Text=connamestr)
#         return con, ""