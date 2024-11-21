import re

from Log import Log, LogSetHeader, LogError
from HelpersPackage import CompressWhitespace, ConvertHTMLishCharacters, RemoveTopBracketedText, FindNextBracketedText
from HelpersPackage import CrosscheckListElement, ScanForBracketedText

from FanzineDateTime import FanzineDateRange
from LocalePage import LocaleHandling
from Conventions import Conventions, IndexTableSingleNameEntry, IndexTableNameEntry, ConInstanceInfo
import F3Page


###########
# Read through all F3Pages and build up a structure of conventions
# We do this by first looking at all conseries pages and extracting the info from their convention tables.
# (Later we'll get more info by reading the individual con pages.)

# Note: There are three convention entities
#       The con series (e.g., Boskone, Westercon)
#       The convention (e.g., Boskone 23, Westercon 18)
#       IndexTableEntry: Something to handle the fact that some conventions are members of two or more conseries and some conventions
#           have been scheduled, moved and cancelled.
def ScanF3PagesForConInfo(fancyPagesDictByWikiname: dict[str, F3Page], redirects: dict[str, str]) -> Conventions:

    # Build a list of Con series pages.  We'll use this later to check links when analyzing con index table entries
    conseries: list[str]=[page.Name for page in fancyPagesDictByWikiname.values() if page.IsConSeries]

    # Build the main list of conventions by walking the convention index table on each of the conseries pages
    conventions: Conventions=Conventions()
    for page in fancyPagesDictByWikiname.values():
        Log(f"Processing page: {page.Name}", Flush=True)
        if not page.IsConSeries:    # We could use conseries for this, but it would not be much faster and would result in an extra layer of indent.
            continue

        # Sometimes there will be multiple tables in a con series index page. It's hard to tell which is for what, so we check each of them.
        numcons=len(conventions)
        for index, table in enumerate(page.Tables):
            numcolumns=len(table.Headers)

            # We require that we have convention and date columns, though we allow alternative column names
            conColumn=CrosscheckListElement(["Convention", "Convention Name", "Name", "Con"], table.Headers)
            if conColumn is None:
                LogError(f"***Can't find Convention column in table {index+1} of {len(page.Tables)} on page {page.Name}", Print=False)
                continue

            dateColumn=CrosscheckListElement(["Date", "Dates"], table.Headers)
            if dateColumn is None:
                LogError(f"***Can't find dates column in table {index+1} of {len(page.Tables)} on page {page.Name}",  Print=False)
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
                # if "Swancon 1" not in row[0]:
                #     continue
                Log(f"Processing: {page.Name}  row: {row}")
                # Skip rows with merged columns, and also rows where either the date cell or the convention name cell is empty
                if len(row) < numcolumns or conColumn >= numcolumns or dateColumn>= numcolumns or len(row[conColumn]) == 0 or len(row[dateColumn]) == 0:
                    Log(f"Problem with row: {len(row)=}, {numcolumns=}, {conColumn=}, {dateColumn=}")
                    continue

                # Check the row for (virtual) in any of several form. If found, set the virtual flag and remove the text from the line
                virtual=False
                # Check each column in turn.  (It would be better if we had a standard. Oh, well.)
                for idx, cell in enumerate(row):
                    v2, col=ScanForVirtual(cell)
                    if v2:
                        row[idx]=cell  # Update the cell with the virtual flag removed
                    virtual=virtual or v2
                Log(f"{virtual=}", Flush=True)

                location=""
                if locColumn is not None:
                    location=row[locColumn].strip()

                # ............................................
                # Now handle the names and dates columns.  Get the corresponding convention name(s) and dates.
                nameEntryList=ExtractConNameInfo(row[conColumn], conseries)
                dateEntryList=ExtractDateInfo(row[dateColumn], page.Name, row)      #TODO: Really should return a IndexTableDateEntry(() object

                # Update nameEntryList to deal with those convention index tables which point to a convention via a redirect.
                for nameentry in nameEntryList:
                    if nameentry.PageName in redirects:
                        nameentry.PageName=redirects[nameentry.PageName]

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
                    #Log(f"No names found in row: {row}", Flush=True)
                    continue

                if len(nameEntryList) == len(dateEntryList):
                    # Easy-peasy. N cons with N dates.
                    # Either a boring con that was simply held as scheduled or one which was renamed when it went to a new date.
                    for i, date in enumerate(dateEntryList):
                        if date.Cancelled:      # If the date is marked as cancelled, but not the name,copy the cancellation over
                            nameEntryList[i].Cancelled=True
                    if virtual:
                        for name in nameEntryList:
                            if not name.Cancelled:
                                name.Virtual=True
                    conventions.Append(ConInstanceInfo(Names=nameEntryList, Location=location, Date=dateEntryList[0]))
                    #Log(f"Done processing (3): {row}", Flush=True)
                    continue

                if len(nameEntryList) == 1 and len(dateEntryList) > 1:
                    # This is the case of a convention which was postponed and perhaps cancelled, but retained the same name.  One con, two (or more) dates.

                    # Are *all* the dates marked as cancelled?
                    allGone=True
                    for date in dateEntryList:
                        if not date.Cancelled:
                            AllGone=False
                    if allGone:
                        nameEntryList[0].Cancelled=True

                    if virtual:
                        for name in nameEntryList:
                            if not name.Cancelled:
                                name.Virtual=True

                    for date in dateEntryList:
                        conventions.Append(ConInstanceInfo(Names=nameEntryList, Location=location, Date=date))
                    #Log(f"Done processing (2): {row}", Flush=True)
                    continue

                if len(nameEntryList) > 1 and len(dateEntryList) == 1:
                    # This is a case of a con with two or more names.  E.g., "[[DSC 35]] / MidSouthCon 17"
                    if dateEntryList[0].Cancelled:
                        for name in nameEntryList:
                            name.Cancelled=True

                    if virtual:
                        for name in nameEntryList:
                            if not name.Cancelled:
                                name.Virtual=True

                    conventions.Append(ConInstanceInfo(Names=nameEntryList, Location=location, Date=dateEntryList[0]))
                    #Log(f"Done processing (1): {row}", Flush=True)
                    continue

                # The leftovers will be uncommon, but we still do need to handle them.
                Log(" ", Flush=True)
                LogError(f"ScanF3PagesForConInfo() Name/date combinations not yet handled: {page.Name}:  row={row}") #{len(dateEntryList)=}  {len(nameEntryList)=}

        Log(f"Completed conseries: {page.Name} num={len(conventions)-numcons}", Flush=True)
    Log("Completed run through of fancyPagesDictByWikiname.values()", Flush=True)



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
                Log(f" {page.Name=}  gets {loc=}", Flush=True)
                continue

            # If it doesn't have a Locale, we search through its text for something that looks like a placename.
            #TODO: Shouldn't we move this upwards and store the derived location in otherwise-empty page.Locales?
            locale=LocaleHandling().ScanConPageforLocale(page.Source)
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

    dateTextCleaned=datetext

    # First, deal with annoying use of templates
    if "{{" in dateTextCleaned:
        dateTextCleaned=re.sub(r"{{([^}]*?)\|(.*?)}}", r"\2", dateTextCleaned)

    # Ignore anything in trailing parenthesis. (e.g, "(Easter weekend)", "(Memorial Day)")
    dateTextCleaned=re.sub(r"\(.*\)\s?$", "", dateTextCleaned)  # TODO: Note that this is greedy. Is that the correct thing to do?
    # Convert the HTML whitespace characters some people have inserted into their ascii equivalents and then compress all spans of whitespace into a single space.

    # Remove leading and trailing spaces
    dateTextCleaned=CompressWhitespace(dateTextCleaned).strip()
    # Now look for dates. There are many cases to consider:
    # 1: date                    A simple date (note that there will never be two simple dates in a dates cell)
    # 2: <s>date</s>             A canceled con's date
    # 3: <s>date</s> date        A rescheduled con's date
    # 4: <s>date</s> <s>date</s> A rescheduled and then cancelled con's dates
    # 5: <s>date</s> <s>date</s> date    A twice-rescheduled con's dates
    # m=re.match("^(:?(<s>.+?</s>)\s*)*(.*)$", dateTextCleaned)
    pat="<s>.+?</s>"
    ds=re.findall(pat, dateTextCleaned)
    if len(ds) > 0:
        dateTextCleaned=re.sub(pat, "", dateTextCleaned).strip()
    if len(dateTextCleaned) > 0:
        ds.append(dateTextCleaned)
    ds=[x for x in ds if x != ""]  # Remove empty matches
    if len(ds) == 0:
        Log(f"Date error: {dateTextCleaned}")
        return []
    # Examine the dates in turn
    dates: list[FanzineDateRange]=[]
    for d in ds:
        c, s=ScanForBracketedText(d, "s")
        dr=FanzineDateRange().Match(s)
        dr.Cancelled=c
        if dr.Duration() > 7:
            LogError(f"??? convention has long duration: {dr}")
        if not dr.IsEmpty():
            dates.append(dr)
    if len(dates) == 0:
        LogError(f"***No dates found - {name}:  {dateTextCleaned=}  {row=}")
    elif len(dates) == 1:
        Log(f"{name}  row: {row}: 1 date: {dates[0]}", Print=False)
    else:
        Log(f"{name}  row: {row}: {len(dates)} dates: {dates[0]}")
        for d in dates[1:]:
            Log(f"           {d}", Print=False)

    return dates

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
    Log(f"ExtractConNameInfo('{nameText})'")

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
        nameTextCleaned=re.sub(r"{{([^}]*?)\|(.*?)}}", r"\2", nameTextCleaned)

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
                lead2, _, content2, remainder2=FindNextBracketedText(name2)
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
            entryList.Append(IndexTableSingleNameEntry(PageName=link2, Text=text2, Lead=lead2, Remainder=remainder2, Cancelled=cancelled, Virtual=v))

    return entryList



def SplitByTopLevelSlashes(nameTextCleaned) -> list[str]:
    # First, split the text into pieces by "/" *outside* of square brackets
    listofslashlocs=[-1]        # Starting point for the first range if there is one.
    depthSquare=0
    depthPointy=0
    for i in range(len(nameTextCleaned)):
        if nameTextCleaned[i] == "[":
            depthSquare+=1
        elif nameTextCleaned[i] == "]":
            depthSquare-=1
        elif nameTextCleaned[i] == "<":
            depthPointy-=1
        elif nameTextCleaned[i] == ">":
            depthPointy+=1
        elif nameTextCleaned[i] == "/" and depthSquare == 0 and depthPointy == 0:
            listofslashlocs.append(i)
    names: list[str]=[]
    if len(listofslashlocs) == 1:
        names=[nameTextCleaned]  # If no top-level slashes were found, we have a list of one name
    else:
        listofslashlocs.append(len(nameTextCleaned))    # This gives us the ending index for the last piece.
        for i in range(len(listofslashlocs)-1):
            names.append(nameTextCleaned[listofslashlocs[i]+1:listofslashlocs[i+1]])

    return names


#---------------------------------------------------------------------------
# Scan for a virtual flag
# Return True/False and the remaining text after the V-flag is removed
def ScanForVirtual(s: str) -> tuple[bool, str]:
    pattern = r"\(?(:?virtual|\(online\)|held online|moved online|virtual convention)\)?"        # The () around online are because we do not want to match online w?o parens

    # First look for one of the alternatives (contained in parens) *anywhere* in the text
    newval = re.sub(pattern, "", s, flags=re.IGNORECASE)  # Check w/parens 1st so that if parens exist, they get removed.
    if s != newval:
        return True, newval.strip()

    # Now look for alternatives by themselves.  So we don't pick up junk, we require that the non-parenthesized alternatives be alone in the cell
    newval = re.sub(r"\s*" + pattern + r"\s*$", "", s, flags=re.IGNORECASE)       #TODO: Is this pattern anchored to the start of the text? Should it be?
    if s != newval:
        return True, newval.strip()

    return False, s
