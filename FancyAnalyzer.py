from __future__ import annotations
from typing import Dict, List, Tuple, Set, Optional, Union
from dataclasses import dataclass

import os
import re
from datetime import datetime

from F3Page import F3Page, DigestPage, TagSet
from Log import Log, LogOpen, LogSetHeader
from HelpersPackage import WindowsFilenameToWikiPagename, SplitOnSpan, WikiExtractLink, CrosscheckListElement
from ConInfo import ConInfo
from FanzineIssueSpecPackage import FanzineDateRange


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

#TODO: Revise this


# There will be a dictionary, nameVariants, indexed by every form of every name. The value will be the canonical form of the name.
# There will be a second dictionary, people, indexed by the canonical name and containing an unordered list of F3Reference structures
# A F3Reference will contain:
#       The canonical name
#       The as-used name
#       An importance code (initially 1, 2 or 3 with 3 being least important)
#       If a reference to Fancy, the name of the page (else None)
#       If a reference to fanac.org, the URL of the relevant page (else None)
#       If a redirect, the redirect name

fancySitePath=r"C:\Users\mlo\Documents\usr\Fancyclopedia\Python\site"   # A local copy of the site maintained by FancyDownloader
LogOpen("Log.txt", "Error.txt")

# The local version of the site is a pair (sometimes also a folder) of files with the Wikidot name of the page.
# <name>.txt is the text of the current version of the page
# <name>.xml is xml containing meta date. The metadata we need is the tags
# If there are attachments, they're in a folder named <name>. We don't need to look at that in this program

# Create a list of the pages on the site by looking for .txt files and dropping the extension
Log("***Querying the local copy of Fancy 3 to create a list of all Fancyclopedia pages")
Log("   path='"+fancySitePath+"'")
allFancy3PagesFnames = [f[:-4] for f in os.listdir(fancySitePath) if os.path.isfile(os.path.join(fancySitePath, f)) and f[-4:] == ".txt"]
allFancy3PagesFnames = [f for f in allFancy3PagesFnames if not f.startswith("index_")]     # Drop index pages
allFancy3PagesFnames = [f for f in allFancy3PagesFnames if not f.endswith(".js")]     # Drop javascript page
#allFancy3PagesFnames= [f for f in allFancy3PagesFnames if f[0] in "A"]        # Just to cut down the number of pages for debugging purposes
#allFancy3PagesFnames= [f for f in allFancy3PagesFnames if f[0:6].lower() == "windyc" or f[0:5].lower() == "new z"]        # Just to cut down the number of pages for debugging purposes
#allFancy3PagesFnames= [f for f in allFancy3PagesFnames if f[0:6].lower() == "philco"]        # Just to cut down the number of pages for debugging purposes

excludedPrefixes=["_admin", "Template;colon", "User;colon", "Log 2"]
for prefix in excludedPrefixes:
    allFancy3PagesFnames = [f for f in allFancy3PagesFnames if not f.startswith(prefix)]     # Drop various tool, admin, etc., pages

excludedPages=["Admin", "Standards", "Test Templates"]
allFancy3PagesFnames=[f for f in allFancy3PagesFnames if f not in excludedPages]

Log("   "+str(len(allFancy3PagesFnames))+" pages found")

fancyPagesDictByWikiname: Dict[str, F3Page]={}     # Key is page's name on the wiki; Val is a FancyPage class containing all the references on the page

Log("***Scanning local copies of pages for links")
for pageFname in allFancy3PagesFnames:
    val=DigestPage(fancySitePath, pageFname)
    if val is not None:
        fancyPagesDictByWikiname[val.Name]=val
    # Print a progress indicator
    l=len(fancyPagesDictByWikiname)
    if l%1000 == 0:
        if l>1000:
            Log("--", noNewLine=True)
        if l%20000 == 0:
            Log("")
        Log(str(l), noNewLine=True)
Log("   "+str(len(fancyPagesDictByWikiname))+" semi-unique links found")

# Build a locale database
Log("\n\n***Building a locale dictionary")
locales: Set[str]=set()  # We use a set to eliminate duplicates and to speed checks
for page in fancyPagesDictByWikiname.values():
    if page.IsLocale:
        LogSetHeader("Processing Locale "+page.Name)
        locales.add(page.Name)
    else:
        if page.Redirect != "" and page.Redirect in fancyPagesDictByWikiname.keys():
            if fancyPagesDictByWikiname[page.Redirect].IsLocale:
                LogSetHeader("Processing Locale "+page.Name)
                locales.add(page.Name)


# Convert names like "Chicago" to "Chicago, IL"
# We look through the locales database for names that are proper extensions of the input name
# First create the dictionary we'll need
localeBaseForms: Dict[str, str]={}  # It's defined as a dictionary with the value being the base form of the key
for locale in locales:
    # Look for names of the form Name,ST
    m=re.match("^([A-Za-z .]*),\s([A-Z]{2})$", locale)
    if m is not None:
        city=m.groups()[0]
        state=m.groups()[1]
        localeBaseForms.setdefault(city, city+", "+state)

# Find the base form of a locale.  E.g., the base form of "Cambridge, MA" is "Boston, MA".
def BaseFormOfLocaleName(localeBaseForms: Dict[str, str], name: str) -> str:
    # Handle the (few) special cases where names may be confusing.
    # There are certain names which are the names of minor cities and towns (usually written as "Name, XX") and also important cities which are written just "Name"
    # E.g., "London, ON" and "London" or "Dublin, OH" and "Dublin"
    # When the name appears without state (or whatever -- this is mostly a US & Canada problem) if it's in the list below, we assume it's a base form
    # Note that we only add to this list when there is a *fannish* conflict.
    basetable=["London", "Dublin"]
    if name in basetable:
       return name

    # OK, try to find a base name
    if name in localeBaseForms.keys():
        return localeBaseForms[name]
    return name

# The current algorithm messes up multi-word city names and only catches the last word.
# Correct the ones we know of to the full name.
multiWordCities={
    "Angeles, CA": "Los",
    "Antonio, TX": "San",
    "Barbara, CA": "Santa",
    "Beach, CA": ["Long", "Huntington"],
    "Beach, FL": ["West Palm", "Cocoa", "Palm"],
    "Beach, VA": "Virginia",
    "Bend, IN": "South",
    "Brook, IL": "Oak",
    "Brook, LI": "Stony",
    "Brook, NJ": "Saddle",
    "Brook, NY": ["Stony", "Rye"],
    "Brunswick, NJ": "New",
    "Carrollton, MD": "New",
    "Charles, IL": "St.",
    "Christi, TX": "Corpus",
    "City, IA": "Iowa",
    "City, KY": "Park",
    "City, MO": "Kansas",
    "City, OK": "Oklahoma",
    "City, UT": "Salt Lake",
    "City, VA": "Crystal",
    "Collins, CO": "Fort",
    "Creek, CA": "Walnut",
    "Creek, MI": "Battle",
    "Diego, CA": "San",
    "Elum, WA": "Cle",
    "Falls, NY": "Niagara",
    "Francisco, CA": "San",
    "Grande, AZ": "Casa",
    "Green, KY": "Bowling",
    "Guardia, NY": "La",
    "Harbor, NH": "Center",
    "Heights, IL": "Arlington",
    "Heights, NJ": "Hasbrouck",
    "Hill, NJ": "Cherry",
    "Island, NY": "Long",
    "Jose, CA": "San",
    "Juan, PR": "San",
    "Lac, WI": "Fond du",
    "Laoghaire, Ireland": "Dun",
    "Lake, OH": "Indian",
    "Lauderdale, FL": "Fort",
    "Laurel, NJ": "Mt.",
    "Louis, MO": "St.",
    "Luzerne, NY": "Lake",
    "Mateo, CA": "San",
    "Moines, IA": "Des",
    "Mountain, GA": "Pine",
    "Oak, FL": "Live",
    "Orleans, LA": "New",
    "Park, AZ": "Litchfield",
    "Park, MD": "Lexington",
    "Park, MN": ["St. Louis", "Brooklyn"],
    "Paso, TX": "El",
    "Pass, WA": "Snoqualmie",
    "Paul, MN": "St.",
    "Petersburg, FL": "St.",
    "Plainfield, NJ": "South",
    "Plains, NY": "White",
    "Point, NC": "High",
    "Rock, AR": ["Little", "North Little"],
    "Rosa, CA": "Santa",
    "Sacromento, CA": "West",
    "Sheen, UK": "East",
    "Spring, MD": "Silver",
    "Springs, CO": "Colorado",
    "Springs, NY": "Saratoga",
    "Station, TX": "College",
    "Town, NY": "Rye",
    "Vegas, NV": "Las",
    "Vernon, WA": "Mount",
    "Way, WA": "Federal",
    "York, NY": "New"
}

# Look for a pattern of the form:
#   in Word, XX
#   where Word is one or more strings of letters each with an initial capital, the comma is optional, and XX is a pair of upper case letters
# Note that this will also pick up roman-numeraled con names, E.g., Fantasycon XI, so we need to remove these later
def ScanForLocales(s: str) -> Optional[Set[str]]:

    # Find the first locale
    # Detect locales of the form Name [Name..Name], XX  -- One or more capitalized words followed by an optional comma followed by exactly two UC characters
    # ([A-Z][a-z]+\]*,?\s)+     Picks up one or more leading capitalized, space (or comma)-separated words
    # \[*  and  \]*             Lets us ignore spans of [[brackets]]
    # The "[^a-zA-Z]"           Prohibits another letter immediately following the putative 2-UC state
    s1=s.replace("[", "").replace("]", "")   # Remove brackets
    m=re.search("in ([A-Z][a-z]+\s+)?([A-Z][a-z]+\s+)?([A-Z][a-z]+,?\s+)([A-Z]{2})[^a-zA-Z]", " "+s1+" ")    # The extra spaces are so that there is at least one character before and after a possible locale
    if m is not None and len(m.groups()) > 1:
        groups=[x for x in m.groups() if x is not None]
        city=" ".join(groups[0:-1])
        city=city.replace(",", " ")                         # Get rid of commas
        city=re.sub("\s+", " ", city).strip()               # Multiple spaces go to single space and trim the result
        city=city.split()

        state=groups[-1].strip()

        impossiblestates = {"SF", "MC", "PR", "II", "IV", "VI", "IX", "XI", "XX", "VL", "XL", "LV", "LX"}  # PR: Progress Report; others Roman numerals; "LI" is allowed because of Long Island
        if state not in impossiblestates:
            # City should consist of one or more space-separated capitalized tokens. Split them into a list
            if len(city) > 0:
                skippers = {"Astra", "Con"}  # Second word of multi-word con names
                if city[-1] not in skippers:
                    # OK, now we know we have at least the form "in Xxxx[,] XX", but there may be many capitalized words before the Xxxx.
                    # If not -- if we have *exactly* "in Xxxx[,] XX" -- then we have a local (as best we can tell).  Return it.
                    loc = city[-1]+", "+state
                    if len(city) == 1:
                        return {loc}
                    # Apparently we have more than one leading word.  Check the last word+state against the multiWordCities dictionary.
                    # If the multi-word city is found, we're good.
                    if loc in multiWordCities.keys():
                        # Check the preceding token in the name against the token in multiWordCities
                        tokens=multiWordCities[loc]
                        if type(tokens) == str:
                            if tokens == " ".join(city[:-1]):
                                return {tokens+" "+loc}
                        else:
                            # It's a list of strings
                            for token in tokens:
                                if token == " ".join(city[:-1]):
                                    return {token+" "+loc}


    # OK, we can't find the Xxxx, XX pattern
    # Look for 'in'+city+[,]+spelled-out country
    # We'll look for a country name preceded by the word 'in' and one or two Capitalized words
    countries=["Australia", "Belgium", "Bulgaria", "Canada", "China", "England", "Germany", "Holland", "Ireland", "Israel", "Italy", "New Zealand", "Netherlands", "Norway", "Sweden", "Finland", "Japan", "France",
               "Poland", "Russia", "Scotland", "Wales"]
    out: Set[str]=set()
    s1=s.replace("[", "").replace("]", "")   # Remove brackets
    splt = SplitOnSpan(",.\s", s1)  # Split on spans of comma, period, and space
    for country in countries:
        try:
            loc=splt.index(country)
            if loc > 2:     # Minimum is 'in City, Country'
                locale=country
                sep=", "
                for i in range(1,6):    # City can be up to five tokens
                    if loc-i < 0:
                        break
                    if re.match("^[A-Z]{1}[a-z]+$", splt[loc-i]):   # Look for Xxxxx
                        locale=splt[loc-i]+sep+locale
                    if splt[loc-i-1] == "in":
                        return {locale}
                    sep=" "
        except ValueError as e:
            continue

    # Look for the pattern "in [[City Name]]"
    # This has the fault that it can find something like "....in [[John Campbell]]'s report" and think that "John Campbell" is a locale.
    # Fortunately, this will nearly always happen *after* the first sentence which contains the actual locale, and we ignore second and later hits
        # Pattern:
        # Capture "in" followed by "[[" followed by a group
        # The group is a possibly repeated non-capturing group
        #       which is a UC letter followed by one or more letters followed by an optional period or comma followed by zero or more spaces
        # ending with "]]"
    lst=re.findall("in \[\[((?:[A-Z][A-Za-z]+[.,]?\s*)+)]]", s)
    if len(lst) > 0:
        out.add(BaseFormOfLocaleName(localeBaseForms, lst[0]))
    return out


Log("***Analyzing convention series tables")

# Scan for a virtual flag
# Return True/False and remaining text after V-flag is removed
def ScanForVirtual(input: str) -> Tuple[bool, str]:
    # First look for the alternative contained in parens *anywhere* in the text
    pat = "\((:?virtual|online|held online|moved online|virtual convention)\)"
    newval = re.sub(pat, "", input,
                    flags=re.IGNORECASE)  # Check w/parens 1st so that if parens exist, they get removed.
    if input != newval:
        return True, newval.strip()
    # Now look for alternatives by themselves.  So we don't pick up junk, we require that the non-parenthesized alternatives be alone in the cell
    newval = re.sub("\s*" + pat + "\s*$", "", input, flags=re.IGNORECASE)
    if input != newval:
        return True, newval.strip()
    return False, input

# Scan for text bracketed by <s>...</s>
# Return True/False and remaining text after <s> </s> is removed
def ScanForS(input: str) -> Tuple[bool, str]:
    m=re.match("\w*<s>(.*)</s>\w*$", input)
    if m is None:
        return False, input
    return True, m.groups()[0]

# Create a list of convention instances with useful information about them stored in a ConInfo structure
conventions: List[ConInfo]=[]
for page in fancyPagesDictByWikiname.values():

    # First, see if this is a Conseries page
    if page.IsConSeries:
        LogSetHeader("Processing "+page.Name)
        # We'd like to find the columns containing:
        locColumn=None     # The convention's location
        conColumn=None     # The convention's name
        dateColumn=None    # The conventions dates
        for index, table in enumerate(page.Tables):
            numcolumns=len(table.Headers)

            listLocationHeaders=["Location"]
            locColumn=CrosscheckListElement(listLocationHeaders, table.Headers)
            # We don't log a missing location column because that is common and not an error -- we'll try to get the location later from the con instance's page

            listNameHeaders=["Convention", "Convention Name", "Name"]
            conColumn=CrosscheckListElement(listNameHeaders, table.Headers)
            if conColumn is None:
                Log("***Can't find Convention column in table "+str(index+1)+" of "+str(len(page.Tables)), isError=True)

            listDateHeaders=["Date", "Dates"]
            dateColumn=CrosscheckListElement(listDateHeaders, table.Headers)
            if conColumn is None:
                Log("***Can't find Dates column in table "+str(index+1)+" of "+str(len(page.Tables)), isError=True)

            # If we don't have a convention column and a date column we skip the whole table.
            if conColumn is not None and dateColumn is not None:

                # Walk the convention table, extracting the individual conventions
                # (Sometimes there will be multiple table
                if table.Rows is None:
                    Log("***Table "+str(index+1)+" of "+str(len(page.Tables))+"has no rows", isError=True)
                    continue

                for row in table.Rows:
                    LogSetHeader("Processing: "+page.Name+"  row: "+str(row))
                    # Skip rows with merged columns, and rows where either the date or convention cell is empty
                    if len(row) < numcolumns-1 or len(row[conColumn]) == 0  or len(row[dateColumn]) == 0:
                        continue

                    # If the con series table has a location column, extract the location
                    conlocation=""
                    if locColumn is not None:
                        if locColumn < len(row) and len(row[locColumn]) > 0:
                            loc=WikiExtractLink(row[locColumn])
                            conlocation=BaseFormOfLocaleName(localeBaseForms, loc)

                    # Check the row for (virtual) in any form. If found, set the virtual flag and remove the text from the line
                    virtual=False
                    for idx, col in enumerate(row):
                        v2, col=ScanForVirtual(col)
                        if v2:
                            row[idx]=col      # Update row with the virtual flag removed
                        virtual=virtual or v2
                    Log("Virtual="+str(virtual))

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
                    p=re.compile("\(.*\)\s?$")  # Note that this is greedy. Is that the correct things to do?
                    datetext=re.sub("\(.*\)\s?$", "", datetext)
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
                    if len(ds) is None:
                        Log("Date error: "+datetext)
                        continue

                    # We have N groups up to N-1 of which might be None
                    dates:List[FanzineDateRange]=[]
                    for d in ds:
                        if d is not None and len(d) > 0:
                            c, s=ScanForS(d)
                            dr=FanzineDateRange().Match(s)
                            dr.Cancelled=c
                            if dr.Duration() > 6:
                                Log("??? convention has long duration: "+str(dr), isError=True)
                            if not dr.IsEmpty():
                                dates.append(dr)

                    if len(dates) == 0:
                        Log("***No dates found", isError=True)
                    elif len(dates) == 1:
                        Log("1 date: "+str(dates[0]))
                    else:
                        Log(str(len(dates))+" dates: " + str(dates[0]))
                        for d in dates[1:]:
                            Log("           " + str(d))


                    # Get the corresponding convention name(s).
                    context=row[conColumn]
                    # Clean up the text
                    context=context.replace("[[", "@@").replace("]]", "%%")  # The square brackets are Regex special characters. This substitution makes the patterns simpler to read
                    # Convert the HTML characters some people have inserted into their ascii equivalents
                    context=context.replace("&nbsp;", " ").replace("&#8209;", "-")
                    # And get rid of hard line breaks
                    context=context.replace("<br>", " ")
                    # In some pages we italicize or bold the con's name, so remove spans of single quotes 2 or longer
                    context=re.sub("[']{2,}", "", context)

                    context=context.strip()

                    if context.count("@@") != context.count("%%"):
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
                    class ConName:
                        #def __init__(self, Name: str="", Link: str="", Cancelled: bool=False):
                        Name: str=""
                        Cancelled: bool=False
                        Link: str=""

                        def __lt__(self, val: ConName) -> bool:
                            return self.Name < val.Name

                    def SplitConText(constr: str) -> Tuple[str, str]:
                        # Now convert all link|text to separate link and text
                        # Do this for s1 and s2
                        m=re.match("@@(.+)\|(.+)%%$", constr)       # Split xxx|yyy into xxx and yyy
                        if m is not None:
                            return m.groups()[0], m.groups()[1]
                        m = re.match("@@(.+)%%$", constr)  # Split xxx|yyy into xxx and yyy
                        if m is not None:
                            return "", m.groups()[0]
                        return "", constr

                    # We assume that the cancelled con names lead the uncancelled ones
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
                        pat="^(@@(:?.*?)%%)"
                        m=re.match(pat, constr)
                        if m is not None:
                            s=m.groups()[0]
                            constr=re.sub(pat, "", constr).strip()  # Remove the matched part and trim whitespace
                            l, t=SplitConText(s)
                            con=ConName(Name=t, Link=l, Cancelled=False)
                            return con, constr

#TODO:  What's left may be a bare con name or it may be a keyword like "held online" or "virtual".  Need to check this on real data
                        if len(constr) > 0:
                            if constr[0] == ":":
                                return None, ""
                            if ":" in constr:
                                constr=constr.split(":")[0]
                            con=ConName(Name=constr)
                            return con, ""

                    cons: List[Union[ConName, List[ConName]]]=[]
                    # Do we have "/" in the con name that is not part of a </s> and not part of a fraction? If so, we have alternate names, not separate cons
                    # The strategy here is to recognize the '/' which are *not* con name separators and turn them into '&&&', then split on the remaining '/' and restore the real ones
                    def replacer(matchObject) -> str:   # This generates the replacement text when used in a re.sub() call
                        if matchObject.group(1) is not None and matchObject.group(2) is not None:
                            return matchObject.group(1)+"&&&"+matchObject.group(2)
                    context=re.sub("(<)/([A-Za-z])", replacer, context)  # Hide the '/' in things like </xxx>
                    context=re.sub("([0-9])/([0-9])", replacer, context)    # Hide the '/' in fractions
                    contextlist=re.split("/", context)
                    contextlist=[x.replace("&&&", "/").strip() for x in contextlist]    # Restore the real '/'s
                    context=context.replace("&&&", "/").strip()
                    if len(contextlist) > 1:
                        contextlist=[x.strip() for x in contextlist if len(x.strip()) > 0]
                        alts: List[ConName]=[]
                        for con in contextlist:
                            c, _=NibbleCon(con)
                            if c is not None:
                                alts.append(c)
                        alts.sort()     # Sort the list so that when this list is created from two or more different convention idnex tables, it looks the same and dups can be removed.
                        cons.append(alts)
                    else:
                        # Ok, we have one or more names and they are for different cons
                        while len(context) > 0:
                            con, context=NibbleCon(context)
                            if con is None:
                                break
                            cons.append(con)

                    # Now we have cons and dates and need to create the appropriate convention entries.
                    if len(cons) == 0 or len(dates) == 0:
                        Log("Scan abandoned: ncons="+str(len(cons))+"  len(dates)="+str(len(dates)), isError=True)
                        continue

                    # Don't add duplicate entries
                    def AppendCon(ci: ConInfo) -> None:
                        hits=[x for x in conventions if ci.NameInSeriesList == x.NameInSeriesList and ci.DateRange == x.DateRange and ci.Cancelled == x.Cancelled and ci.Virtual == x.Virtual and ci.Override == x.Override]
                        if len(hits) == 0:
                            conventions.append(ci)
                        else:
                            Log("AppendCon: duplicate - "+str(ci)+"   and   "+str(hits[0]))
                            # If there are two sources for the convention's location and one is empty, use the other.
                            if len(hits[0].Loc) == 0:
                                hits[0].SetLoc(ci.Loc)

                    # The first case we need to look at it whether cons[0] has a type of list of ConInfo
                    # This is one con with multiple names
                    if type(cons[0]) is list:
                        # By definition there is only one element. Extract it.  There may be more than one date.
                        assert len(cons) == 1 and len(cons[0]) > 0
                        cons=cons[0]
                        for dt in dates:
                            override=""
                            cancelled=dt.Cancelled
                            dt.Cancelled = False
                            for co in cons:
                                cancelled=cancelled or co.Cancelled
                                if len(override) > 0:
                                    override+=" / "
                                override+="[["
                                if len(co.Link) > 0:
                                    override+=co.Link+"|"
                                override+=co.Name+"]]"
                            v = False if cancelled else virtual
                            ci=ConInfo(_Link="dummy", NameInSeriesList="dummy", Loc=conlocation, DateRange=dt, Virtual=v, Cancelled=cancelled)
                            ci.Override=override
                            AppendCon(ci)
                            Log("#append 1: "+str(ci))
                    # OK, in all the other cases cons is a list[ConInfo]
                    elif len(cons) == len(dates):
                        # Add each con with the corresponding date
                        for i in range(len(cons)):
                            cancelled=cons[i].Cancelled or dates[i].Cancelled
                            dates[i].Cancelled=False    # We've xferd this to ConInfo and don't still want it here because it would print twice
                            v=False if cancelled else virtual
                            ci=ConInfo(_Link=cons[i].Link, NameInSeriesList=cons[i].Name, Loc=conlocation, DateRange=dates[i], Virtual=v, Cancelled=cancelled)
                            if ci.DateRange.IsEmpty():
                                Log("***"+ci.Link+"has an empty date range: "+str(ci.DateRange), isError=True)
                            Log("#append 2: "+str(ci))
                            AppendCon(ci)
                    elif len(cons) > 1 and len(dates) == 1:
                        # Multiple cons all with the same dates
                        for co in cons:
                            cancelled=co.Cancelled or dates[0].Cancelled
                            dates[0].Cancelled = False
                            v=False if cancelled else virtual
                            ci=ConInfo(_Link=co.Link, NameInSeriesList=co.Name, Loc=conlocation, DateRange=dates[0], Virtual=v, Cancelled=cancelled)
                            AppendCon(ci)
                            Log("#append 3: "+str(ci))
                    elif len(cons) == 1 and len(dates) > 1:
                        for dt in dates:
                            cancelled=cons[0].Cancelled or dt.Cancelled
                            dt.Cancelled = False
                            v=False if cancelled else virtual
                            ci=ConInfo(_Link=cons[0].Link, NameInSeriesList=cons[0].Name, Loc=conlocation, DateRange=dt, Virtual=v, Cancelled=cancelled)
                            AppendCon(ci)
                            Log("#append 4: "+str(ci))
                    else:
                        Log("Can't happen! ncons="+str(len(cons))+"  len(dates)="+str(len(dates)), isError=True)


# Compare two locations to see if they match
def LocMatch(loc1: str, loc2: str) -> bool:
    # First, remove '[[' and ']]' from both locs
    loc1=loc1.replace("[[", "").replace("]]", "")
    loc2=loc2.replace("[[", "").replace("]]", "")

    # We want 'Glasgow, UK' to match 'Glasgow', so deal with the pattern of <City>, <Country Code> matching <City>
    m=re.match("^/s*(.*), [A-Z]{2}\s*$", loc1)
    if m is not None:
        loc1=m.groups()[0]
    m=re.match("^/s*(.*), [A-Z]{2}\s*$", loc2)
    if m is not None:
        loc2=m.groups()[0]

    return loc1 == loc2

# OK, all of the con series have been mined.  Now let's look through all the con instances and see if we can get more location information from them.
# (Not all con series tables contain location information.)
# Generate a report of cases where we have non-identical con information from both sources.
with open("Con location discrepancies.txt", "w+", encoding='utf-8') as f:
    for page in fancyPagesDictByWikiname.values():
        # If it's an individual convention page, we search through its text for something that looks like a placename.
        if page.IsConInstance:
            m=ScanForLocales(page.Source)
            if len(m) > 0:
                for place in m:
                    place=WikiExtractLink(place)
                    # Find the convention in the conventions dictionary and add the location if appropriate.
                    conname=page.Redirect
                    listcons=[x for x in conventions if x.NameInSeriesList == conname]
                    for con in listcons:
                        if not LocMatch(place, con.Loc):
                            if con.Loc == "":   # If there previously was no location from the con series page, substitute what we found in the con instance page
                                con.SetLoc(place)
                                continue
                            f.write(conname+": Location mismatch: '"+place+"' != '"+con.Loc+"'\n")

# Normalize convention locations to the standard City, ST form.
Log("***Normalizing con locations")
for con in conventions:
    loc=ScanForLocales(con.Loc)
    if len(loc) > 1:
        Log("  In "+con.NameInSeriesList+"  found more than one location: "+str(loc))
    if len(loc) > 0:
        con.SetLoc=(iter(loc).__next__())    # Nasty code to get one element from the set


# Sort the con dictionary  into date order
Log("Writing Con DateRange oddities.txt")
oddities=[x for x in conventions if x.DateRange.IsOdd()]
with open("Con DateRange oddities.txt", "w+", encoding='utf-8') as f:
    for con in oddities:
        f.write(str(con)+"\n")
conventions.sort(key=lambda d: d.DateRange)

#TODO: Add a list of keywords to find and remove.  E.g. "Astra RR" ("Ad Astra XI")

# ...
Log("Writing Convention timeline (Fancy).txt")
with open("Convention timeline (Fancy).txt", "w+", encoding='utf-8') as f:
    f.write("This is a chronological list of SF conventions automatically extracted from Fancyclopedia 3\n\n")
    f.write("If a convention is missing from the list, it may be due to it having been added only recently, (this list was generated ")
    f.write(datetime.now().strftime("%A %B %d, %Y  %I:%M:%S %p")+" EST)")
    f.write(" or because we do not yet have information on the convention or because the convention's listing in Fancy 3 is a bit odd ")
    f.write("and the program which creates this list isn't parsing it.  In any case, we welcome help making it more complete!\n\n")
    f.write("The list currently has "+str(len(conventions))+" conventions.\n")
    currentYear=None
    currentDateRange=None
    # We're going to write a Fancy 3 wiki table
    # Two columns: Daterange and convention name and location
    # The date is not repeated when it is the same
    # The con name and location is crossed out when it was cancelled or moved and (virtual) is added when it was virtual
    f.write("<tab>\n")
    for con in conventions:
        # Look up the location for this convention
        conloctext=con.Loc

        # Format the convention name and location for tabular output
        if len(con.Override) > 0:
            context=con.Override
        else:
            context="[["+str(con.NameInSeriesList)+"]]"
        if con.Virtual:
            context="''"+context+" (virtual)''"
        else:
            if len(conloctext) > 0:
                context+="&nbsp;&nbsp;&nbsp;<small>("+conloctext+")</small>"

        # Now write the line
        # We have two levels of date headers:  The year and each unique date within the year
        # We do a year header for each new year, so we need to detect when the current year changes
        if currentYear != con.DateRange._startdate.Year:
            # When the current date range changes, we put the new date range in the 1st column of the table
            currentYear=con.DateRange._startdate.Year
            currentDateRange=con.DateRange
            f.write('colspan="2"| '+"<big><big>'''"+str(currentYear)+"'''</big></big>\n")

            # Write the row in two halves, first the date column and then the con column
            f.write(str(con.DateRange)+"||")
        else:
            if currentDateRange != con.DateRange:
                f.write(str(con.DateRange)+"||")
                currentDateRange=con.DateRange
            else:
                f.write("&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;' ' ||")

        if con.Cancelled:
            f.write("<s>"+context+"</s>\n")
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
                                    f.write(fancyPage.Name+" is pointed to by "+inverse+" which is not a Locale\n")

# ...
# Create a dictionary of page references for people pages.
# The key is a page's canonical name; the value is a list of pages at which they are referenced.
peopleReferences: Dict[str, List[str]]={}
Log("***Creating dict of people references")
for fancyPage in fancyPagesDictByWikiname.values():
    if fancyPage.IsPerson and len(fancyPage.OutgoingReferences) > 0:
        peopleReferences.setdefault(fancyPage.Name, [])
        for outRef in fancyPage.OutgoingReferences:
            try:
                if fancyPagesDictByWikiname[outRef.LinkWikiName].IsPerson:
                    peopleReferences.setdefault(outRef.LinkWikiName, [])
                    peopleReferences[outRef.LinkWikiName].append(fancyPage.Name)
            except KeyError:
                Log("****KeyError on "+outRef.LinkWikiName)
# ...
Log("***Writing reports")
# Write out a file containing canonical names, each with a list of pages which refer to it.
# The format will be
#     **<canonical name>
#     <referring page>
#     <referring page>
#     ...
#     **<canonical name>
#     ...
Log("Writing: Referring pages.txt")
with open("Referring pages.txt", "w+", encoding='utf-8') as f:
    for person, referringpagelist in peopleReferences.items():
        f.write("**"+person+"\n")
        for pagename in referringpagelist:
            f.write("  "+pagename+"\n")

# ...
# Now a list of redirects.
# We use basically the same format:
#   **<target page>
#   <redirect to it>
#   <redirect to it>
# ...
# Now dump the inverse redirects to a file
Log("Writing: Redirects.txt")
with open("Redirects.txt", "w+", encoding='utf-8') as f:
    for redirect, pages in inverseRedirects.items():
        f.write("**"+redirect+"\n")
        for page in pages:
            f.write("      ⭦ "+page+"\n")

# Next, a list of redirects with a missing target
Log("Writing: Redirects with missing target.txt")
allFancy3Pagenames=set([WindowsFilenameToWikiPagename(n) for n in allFancy3PagesFnames])
with open("Redirects with missing target.txt", "w+", encoding='utf-8') as f:
    for key in redirects.keys():
        dest=WikiExtractLink(redirects[key])
        if dest not in allFancy3Pagenames:
            f.write(key+" --> "+dest+"\n")


# ...
# Create and write out a file of peoples' names. They are taken from the titles of pages marked as fan or pro

# Ambiguous names will often end with something in parenthesis which need to be removed for this particular file
def RemoveTrailingParens(s: str) -> str:
    return re.sub("\s\(.*\)$", "", s)       # Delete any trailing ()


# Some names are not worth adding to the list of people names.  Try to detect them.
def IsInterestingName(p: str) -> bool:
    if " " not in p and "-" in p:   # We want to ignore names like "Bob-Tucker" in favor of "Bob Tucker"
        #TODO: Deal with hypenated last names
        return False
    if " " in p:                    # If there are spaces in the name, at least one of them needs to be followed by a UC letter or something like "deCordova"f
        if re.search(" ([A-Z]|de|ha|von|Č)", p) is None:  # We want to ignore "Bob tucker"
            return False
    return True

Log("Writing: Peoples rejected names.txt")
peopleNames: Union[Set[str], List[str]]=set()
# First make a list of all the pages labelled as "fan" or "pro"
with open("Peoples rejected names.txt", "w+", encoding='utf-8') as f:
    for fancyPage in fancyPagesDictByWikiname.values():
        if fancyPage.IsPerson:
            peopleNames.add(RemoveTrailingParens(fancyPage.Name))
            # Then all the redirects to one of those pages.
            if fancyPage.Name in inverseRedirects.keys():
                for p in inverseRedirects[fancyPage.Name]:
                    if p in fancyPagesDictByWikiname.keys():
                        peopleNames.add(RemoveTrailingParens(fancyPagesDictByWikiname[p].Redirect))
                        if IsInterestingName(p):
                            peopleNames.add(p)
                        # else:
                        #     f.write("Uninteresting: "+p+"\n")
                    else:
                        Log("Generating Peoples rejected names.txt: "+p+" is not in fancyPagesDictByWikiname")
            # else:
            #     f.write(fancyPage.Name+" Not in inverseRedirects.keys()\n")


with open("Peoples names.txt", "w+", encoding='utf-8') as f:
    peopleNames=list(peopleNames)   # Turn it into a list so we can sort it.
    peopleNames.sort(key=lambda p: p.split()[-1][0].upper()+p.split()[-1][1:]+","+" ".join(p.split()[0:-1]))    # Invert so that last name is first and make initial letter UC.
    for name in peopleNames:
        f.write(name+"\n")


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
    if fancyPage.OutgoingReferences is not None:
        for outRef in fancyPage.OutgoingReferences:
            if fancyPage.IsPerson:
                peopleReferences.setdefault(outRef.LinkWikiName, [])
                peopleReferences[outRef.LinkWikiName].append(fancyPage.Name)

Log("***Writing reports")
# Write out a file containing canonical names, each with a list of pages which refer to it.
# The format will be
#     **<canonical name>
#     <referring page>
#     <referring page>
#     ...
#     **<canonical name>
#     ...
Log("Writing: Referring pages.txt")
with open("Referring pages.txt", "w+", encoding='utf-8') as f:
    for person, referringpagelist in peopleReferences.items():
        f.write("**"+person+"\n")
        for pagename in referringpagelist:
            f.write("  "+pagename+"\n")

# Now a list of redirects.
# We use basically the same format:
#   **<target page>
#   <redirect to it>
#   <redirect to it>
# ...
# Now dump the inverse redirects to a file
Log("Writing: Redirects.txt")
with open("Redirects.txt", "w+", encoding='utf-8') as f:
    for redirect, pages in inverseRedirects.items():
        f.write("**"+redirect+"\n")
        for page in pages:
            f.write("      ⭦ "+page+"\n")

# Next, a list of redirects with a missing target
Log("Writing: Redirects with missing target.txt")
with open("Redirects with missing target.txt", "w+", encoding='utf-8') as f:
    for fancyPage in fancyPagesDictByWikiname.values():
        dest=fancyPage.Redirect
        if dest != "" and dest not in allFancy3Pagenames:
            f.write(fancyPage.Name+" --> "+dest+"\n")


##################
# Create and write out a file of peoples' names. They are taken from the titles of pages marked as fan or pro

# Ambiguous names will often end with something in parenthesis which need to be removed for this particular file
def RemoveTrailingParens(s: str) -> str:
    return re.sub("\s\(.*\)$", "", s)       # Delete any trailing ()

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

Log("Writing: Peoples rejected names.txt")
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
                            f.write("Uninteresting: "+p+"\n")
                    else:
                        Log(p+" does not point to a person's name")
            else:
                f.write(fancyPage.Name+": Good name -- ignored\n")


# De-dupe it
peopleNames=list(set(peopleNames))

Log("Writing: Peoples names.txt")
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
            if tags is not None:
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

Log("Writing: Counts for individual tags.txt")
with open("Tag counts.txt", "w+", encoding='utf-8') as f:
    tagcountslist=[(key, val) for key, val in tagcounts.items()]
    tagcountslist.sort(key=lambda elem: elem[1], reverse=True)
    for tag, count in tagcountslist:
        f.write(tag+": "+str(count)+"\n")

Log("Writing: Counts for tagsets.txt")
with open("Tagset counts.txt", "w+", encoding='utf-8') as f:
    tagsetcountslist=[(key, val) for key, val in tagsetcounts.items()]
    tagsetcountslist.sort(key=lambda elem: elem[1], reverse=True)
    for tagset, count in tagsetcountslist:
        f.write(str(tagset)+": "+str(count)+"\n")

##################
# Now redo the counts, ignoring countries
ignoredTags=adminTags.copy().union(countryTags)
tagcounts, tagsetcounts=ComputeTagCounts(fancyPagesDictByWikiname, ignoredTags)

Log("Writing: Counts for tagsets without country.txt")
with open("Tagset counts without country.txt", "w+", encoding='utf-8') as f:
    for tagset, count in tagsetcounts.items():
        f.write(str(tagset)+": "+str(count)+"\n")


##################
# Now do it again, but this time look at all subsets of the tags (again, ignoring the admin tags)
tagsetcounts: Dict[str, int]={}
for fp in fancyPagesDictByWikiname.values():
    if not fp.IsRedirectpage:
        tagpowerset=set()   # of TagSets
        tags=fp.Tags
        if tags is not None:
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
            i=0

Log("Writing: Counts for tagpowersets.txt")
with open("Tagpowerset counts.txt", "w+", encoding='utf-8') as f:
    for tagset, count in tagsetcounts.items():
        f.write(str(tagset)+": "+str(count)+"\n")

##############
# We want apazine and clubzine to be used in addition to fanzine.  Make a list of
# First make a list of all the pages labelled as "fan" or "pro"
Log("Writing: Apazines and clubzines that aren't fanzines.txt")
with open("Apazines and clubzines that aren't fanzines.txt", "w+", encoding='utf-8') as f:
    for fancyPage in fancyPagesDictByWikiname.values():
        # Then all the redirects to one of those pages.
        if fancyPage.Tags is not None and ("Apazine" in fancyPage.Tags or "Clubzine" in fancyPage.Tags) and "Fanzine" not in fancyPage.Tags:
            f.write(fancyPage.Name+"\n")


##################
# Make a list of all all-upper-case pages which are not tagged initialism.
Log("Writing: Uppercase name which aren't marked as Initialisms.txt")
with open("Uppercase names which aren't marked as initialisms.txt", "w+", encoding='utf-8') as f:
    for fancyPage in fancyPagesDictByWikiname.values():
        # A page might be an initialism if ALL alpha characters are upper case
        if fancyPage.Name == fancyPage.Name.upper():
            fpn=fancyPage.Name.upper()
            # Bail out if it starts with 4 digits -- this is probably a year
            if fpn[:4].isnumeric():
                continue
            # Bail if it begin 'nn which is also likely a year
            if fpn[0] == "'" and fpn[1:3].isnumeric():
                continue
            # We skip certain pages because while they may look like initilaisms, they aren't or because we onl flag con series, and not the individual cons
            if fpn[:4] == "DSC " or fpn[:8] == "CAN*CON " or fpn[:5] == "ICFA " or fpn[:5] == "NJAC " or \
                    fpn[:6] == "OASIS " or fpn[:5] == "OVFF "  or fpn[:6] == "URCON "  or fpn[:5] == "VCON ":
                continue
            # Bail if there are no alphabetic characters
            if fpn.lower() == fpn.upper():
                continue

            # If what's left lacks the Initialism tag, we want to list it
            if fancyPage.Tags is None or "Initialism" not in fancyPage.Tags:
                f.write(fancyPage.Name+": "+str(fancyPage.Tags)+"\n")


##################
# Taggin Oddities
# Make a list of all fans, pros, and mundanes who are not also tagged person
Log("Tagging oddities.txt")
with open("Tagging oddities.txt", "w+", encoding='utf-8') as f:
    f.write("Fans, pros, and mundanes who are not also tagged person\n")
    for fancyPage in fancyPagesDictByWikiname.values():
        # Then all the redirects to one of those pages.
        if ("Pro" in fancyPage.Tags or "Muundane" in fancyPage.Tags or "Fan" in fancyPage.Tags) and "Person" not in fancyPage.Tags:
            f.write(fancyPage.Name+": "+str(fancyPage.Tags)+"\n")

    f.write("\n\nPersons who are not tagged Fan, pro, or mundane\n")
    for fancyPage in fancyPagesDictByWikiname.values():
        # Then all the redirects to one of those pages.
        if "Person" in fancyPage.Tags and "Fan" not in fancyPage.Tags and "Pro" not in fancyPage.Tags and "Mundane" not in fancyPage.Tags:
            f.write(fancyPage.Name+": "+str(fancyPage.Tags)+"\n")

    f.write("\n\nPublishers which are tagged as persons\n")
    for fancyPage in fancyPagesDictByWikiname.values():
        # Then all the redirects to one of those pages.
        if fancyPage.IsPublisher and fancyPage.IsPerson:
            f.write(fancyPage.Name+": "+str(fancyPage.Tags)+"\n")

    f.write("\n\nNicknames which are not persons, fanzines or cons\n")
    for fancyPage in fancyPagesDictByWikiname.values():
        # Then all the redirects to one of those pages.
        if fancyPage.IsNickname and not (fancyPage.IsPerson or fancyPage.IsFanzine or fancyPage.IsConInstance):
            f.write(fancyPage.Name+": "+str(fancyPage.Tags)+"\n")

##################
# Make a list of all Mundanes
Log("Writing: Mundanes.txt")
with open("Mundanes.txt", "w+", encoding='utf-8') as f:
    for fancyPage in fancyPagesDictByWikiname.values():
        # Then all the redirects to one of those pages.
        if fancyPage.IsMundane:
            f.write(fancyPage.Name+": "+str(fancyPage.Tags)+"\n")

##################
# Compute some special statistics to display at fanac.org
Log("Writing: Statistics.txt")
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
            if not fancyPage.IsRedirectpage:
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
    f.write("  Total pages: " + str(npages) + "\n")
    f.write("  All people: " + str(npeople) + "\n")
    f.write("  Fans: " + str(nfans) + "\n")
    f.write("  Fanzines: "+str(nfanzines)+"\n")
    f.write("  APAs: " + str(napas) + "\n")
    f.write("  Clubs: " + str(nclubs) + "\n")
    f.write("  Conventions: " + str(nconinstances) + "\n")