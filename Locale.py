from __future__ import annotations
from typing import Dict, Set, Optional

import re

from F3Page import F3Page
from Log import LogSetHeader
from HelpersPackage import SplitOnSpan

class Locale:
    # A set of the names of all Locale pages
    # We use a set to eliminate duplicates and to speed checks
    locales: Set[str]=set()
    # All locales have a base form (often themselves).
    # Rhis is a dictionary with the value being the base form of the key: both key and value are page names
    localeBaseForms: Dict[str, str]={}

    # Go through the entire set of pages looking for locales and harvest the information
    def Create(self, fancyPagesDictByWikiname: Dict[str, F3Page]) -> None:
        for page in fancyPagesDictByWikiname.values():
            # Add locale pages to the set
            if page.IsLocale:
                LogSetHeader("Found Locale page "+page.Name)
                self.locales.add(page.Name)
            else:
                # If this page is a redirect to a locale page, add this page to the locale set
                # TODO: Do we want all redirects to locale pages or just those tagged as a locale?
                if page.Redirect != "" and page.Redirect in fancyPagesDictByWikiname.keys():
                    if fancyPagesDictByWikiname[page.Redirect].IsLocale:
                        LogSetHeader("Processing Locale redirect "+page.Name)
                        self.locales.add(page.Name)

    # Convert names like "Chicago" to "Chicago, IL"
    # We look through the locales database for names that are proper extensions of the input name
    # First create the dictionary we'll need
    for locale in locales:
        # Look for names of the form Name,ST
        m=re.match("^([A-Za-z .]*),\s([A-Z]{2})$", locale)
        if m is not None:
            city=m.groups()[0]
            state=m.groups()[1]
            localeBaseForms.setdefault(city, city+", "+state)

    # Find the base form of a locale.  E.g., the base form of "Cambridge, MA" is "Boston, MA".
    def BaseFormOfLocaleName(self, name: str) -> str:
        # Handle the (few) special cases where names may be confusing.
        # There are certain names which are the names of minor cities and towns (usually written as "Name, XX") and also important cities which are written just "Name"
        # E.g., "London, ON" and "London" or "Dublin, OH" and "Dublin"
        # When the name appears without state (or whatever -- this is mostly a US & Canada problem) if it's in the list below, we assume it's a base form
        # Note that we only add to this list when there is a *fannish* conflict.
        basetable=["London", "Dublin"]
        if name in basetable:
           return name

        # OK, try to find a base name
        if name in self.localeBaseForms.keys():
            return self.localeBaseForms[name]
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
    def ScanForLocales(self, s: str) -> Optional[Set[str]]:

        # Find the first locale
        # Detect locales of the form Name [Name..Name], XX  -- One or more capitalized words followed by an optional comma followed by exactly two UC characters
        # ([A-Z][a-z]+\]*,?\s)+     Picks up one or more leading capitalized, space (or comma)-separated words
        # \[*  and  \]*             Lets us ignore spans of [[brackets]]
        # The "[^a-zA-Z]"           Prohibits another letter immediately following the putative 2-UC state
        s1=s.replace("[", "").replace("]", "")  # Remove brackets
        m=re.search("in ([A-Z][a-z]+\s+)?([A-Z][a-z]+\s+)?([A-Z][a-z]+,?\s+)([A-Z]{2})[^a-zA-Z]",
                    " "+s1+" ")  # The extra spaces are so that there is at least one character before and after a possible locale
        if m is not None and len(m.groups())>1:
            groups=[x for x in m.groups() if x is not None]
            city=" ".join(groups[0:-1])
            city=city.replace(",", " ")  # Get rid of commas
            city=re.sub("\s+", " ", city).strip()  # Multiple spaces go to single space and trim the result
            city=city.split()

            state=groups[-1].strip()

            impossiblestates={"SF", "MC", "PR", "II", "IV", "VI", "IX", "XI", "XX", "VL", "XL", "LV",
                              "LX"}  # PR: Progress Report; others Roman numerals; "LI" is allowed because of Long Island
            if state not in impossiblestates:
                # City should consist of one or more space-separated capitalized tokens. Split them into a list
                if len(city)>0:
                    skippers={"Astra", "Con"}  # Second word of multi-word con names
                    if city[-1] not in skippers:
                        # OK, now we know we have at least the form "in Xxxx[,] XX", but there may be many capitalized words before the Xxxx.
                        # If not -- if we have *exactly* "in Xxxx[,] XX" -- then we have a local (as best we can tell).  Return it.
                        loc=city[-1]+", "+state
                        if len(city) == 1:
                            return {loc}
                        # Apparently we have more than one leading word.  Check the last word+state against the multiWordCities dictionary.
                        # If the multi-word city is found, we're good.
                        if loc in self.multiWordCities.keys():
                            # Check the preceding token in the name against the token in multiWordCities
                            tokens=self.multiWordCities[loc]
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
        countries=["Australia", "Belgium", "Bulgaria", "Canada", "China", "England", "Germany", "Holland", "Ireland",
                   "Israel", "Italy", "New Zealand", "Netherlands", "Norway", "Sweden", "Finland", "Japan", "France",
                   "Poland", "Russia", "Scotland", "Wales"]
        out: Set[str]=set()
        s1=s.replace("[", "").replace("]", "")  # Remove brackets
        splt=SplitOnSpan(",.\s", s1)  # Split on spans of comma, period, and space
        for country in countries:
            try:
                loc=splt.index(country)
                if loc>2:  # Minimum is 'in City, Country'
                    locale=country
                    sep=", "
                    for i in range(1, 6):  # City can be up to five tokens
                        if loc-i<0:
                            break
                        if re.match("^[A-Z]{1}[a-z]+$", splt[loc-i]):  # Look for Xxxxx
                            locale=splt[loc-i]+sep+locale
                        if splt[loc-i-1] == "in":
                            return {locale}
                        sep=" "
            except ValueError:
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
        if len(lst)>0:
            out.add(Locale().BaseFormOfLocaleName(lst[0]))
        return out


    # Compare two locations to see if they match
    def LocMatch(self, loc1: str, loc2: str) -> bool:
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