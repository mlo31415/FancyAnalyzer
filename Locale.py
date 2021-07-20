from __future__ import annotations
from typing import Dict, Set, List
from dataclasses import dataclass

import re

from F3Page import F3Page
from Log import LogSetHeader, Log
from HelpersPackage import SplitOnSpan, WikidotCononicizeName


############################################################################################
# This class encapsulates our knowledge of Locale pages
# There are four kinds of pages which generate a Locale:
#   A base Locale: typically a metropolitan name in standard form, e.g., Boston, MA).  It is tagged as a Locale and is not a redirect
#   A shortname: Some cities, e.g., Boston, London, New York, are usually referred to without state/country.
#   A non-base Locale: typically a location in a metro area, e.g., Cambridge, MA. It is tagged as a Locale, but redirects to a base Locale
#   A synonym: typically a variant spelling or Wikidot form of a base (or non-base) Locale, e.g., Cambridge_ma. It is a redirect to a Locale, but not tagged as one
@dataclass
class Locale:
    PageName: str=""        # The Fancy 3 page name.
    DisplayName: str=""     # If there's a MediaWiki Displayname override, put it here. Otherwise empty string
    Redirect: str=""        # If this is a redirect page, the page name of the target. Otherwise empty string
    IsTaggedLocale: bool=False    # Is this page tagged "Locale"?
    Basename: str=""        # If PageName is "Boston" this would be "Boston, MA"; otherwise empty

    @property
    # The name of the locale for the world to see.
    def Name(self) -> str:
        return self.PageName

    @property
    def IsLocale(self) -> bool:
        return self.IsTaggedLocale

    @property
    def IsRedirect(self) -> bool:
        return len(self.Redirect) > 0

    @property
    # Is this nothing but a pointer for the Wikidot canonical name of the page?
    def IsWikidot(self) -> bool:
        return self.Redirect and not self.IsTaggedLocale and self.PageName == WikidotCononicizeName(self.PageName)

    @property
    def PreferredName(self) -> str:
        # If this is itself tagged as a Locale we return the page name even if it is a redirect
        # E.g., we return "Cambridge, MA" because it is tagged Locale even though it points to "Boston, MA"
        if self.IsTaggedLocale:
            if len(self.DisplayName) > 0:
                return self.DisplayName
            return self.PageName

        # It's a Locale, but not tagged as one.  Unless it's a error, it's a redirect from a Wikidot canonical name
        if not self.IsWikidot:
            Log(f"@@@Locale page {self.PageName} is not tagged as Locale, but is not in Wikidot format")
            return self.PageName

        # OK, it is not tagged as a Locale and is in Wikidot format.  If it's a redirect, follow the redirect!
        if len(self.Redirect) > 0:
            return self.Redirect    #TODO: should go to redirect's Locale to see if it has some other preferred name

        assert False


    #-------------------------------------------------------------
    # Compare two locations to see if they match
    def LocMatch(self, loc2: str) -> bool:
        # First, remove '[[' and ']]' from both locs
        loc1=self.PageName.replace("[[", "").replace("]]", "")
        loc2=loc2.replace("[[", "").replace("]]", "")

        # We want 'Glasgow, UK' to match 'Glasgow', so deal with the pattern of <City>, <Country Code> matching <City>
        m=re.match("^/s*(.*), [A-Z]{2}\s*$", loc1)
        if m is not None:
            loc1=m.groups()[0]
        m=re.match("^/s*(.*), [A-Z]{2}\s*$", loc2)
        if m is not None:
            loc2=m.groups()[0]

        return loc1 == loc2


############################################################################################
class LocaleDict:
    def __init__(self):
        self.d: Dict[str, Locale]={}

    def __getitem__(self, i: str) -> Locale:
        if i not in self.d.keys():
            Log(f"LocaleDict({i}) does not exist")
            raise IndexError
        return self.d[i]

    def __setitem__(self, i: str, val: Locale) -> None:
        self.d[i]=val

    def __len__(self):
        return len(self.d)

    def values(self):
        return self.d.values()

    def keys(self):
        return self.d.keys()


############################################################################################
class LocaleHandling:
    # A set of the names of all Locale pages
    # We use a set to eliminate duplicates and to speed checks
    locales: LocaleDict=LocaleDict()

    # All locales have a base form (often themselves).
    # This is a dictionary with the value being the base form of the key: both key and value are page names
    localeBaseForms: Dict[str, str]={}

    # We also identify some things as probable locales which are not tagged directly or indirectly as locales
    # Maintain a dict of lists of pages that contain them
    probableLocales: Dict[str, List[str]]={}

    # Go through the entire set of pages looking for locales and harvest the information
    def Create(self, fancyPagesDictByWikiname: Dict[str, F3Page]) -> None:
        for page in fancyPagesDictByWikiname.values():
            # Add locale pages to the set
            if page.IsLocale:
                LogSetHeader("Found Locale page "+page.Name)
                self.locales[page.Name]=Locale(PageName=page.Name, Redirect=page.Redirect, IsTaggedLocale=page.IsLocale, DisplayName=page.DisplayTitle)
            else:
                # If this page is a redirect to a locale page, add this page to the locale set
                # TODO: Do we want all redirects to locale pages or just those tagged as a locale?
                if page.IsRedirectpage and page.Redirect in fancyPagesDictByWikiname.keys() and fancyPagesDictByWikiname[page.Redirect].IsLocale:
                    LogSetHeader("Processing Locale redirect "+page.Name)
                    self.locales[page.Name]=Locale(PageName=page.Name, Redirect=page.Redirect, IsTaggedLocale=page.IsLocale, DisplayName=page.DisplayTitle)

        # Convert names like "Chicago" to "Chicago, IL"
        # We look through the locales database for names that are proper extensions of the input name
        # First create the dictionary we'll need
        for locale in self.locales.values():
            # Look for names of the form 'Name, ST'
            m=re.match("^([A-Za-z .]*),\s([A-Z]{2})$", locale.Name)
            if m is not None:
                city=m.groups()[0]
                state=m.groups()[1]
                self.localeBaseForms.setdefault(city, city+", "+state)

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


    # Looking for <in City, ST> messes up multi-word city names and only catches the last word.
    # Correct the ones we know of to the full name.
    multiWordCities={
        "Angeles, CA": "Los",
        "Antonio, TX": "San",
        "Barbara, CA": "Santa",
        "Beach, CA": ["Long", "Huntington", "Manhattan"],
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
        "City, CA": ["Culver", "Universal"],
        "City, IA": "Iowa",
        "City, KY": "Park",
        "City, MO": "Kansas",
        "City, OK": "Oklahoma",
        "City, PQ": "Quebec",
        "City, UT": "Salt Lake",
        "City, VA": "Crystal",
        "Collins, CO": "Fort",
        "Creek, CA": "Walnut",
        "Creek, MI": "Battle",
        "Diego, CA": "San",
        "Dublin, OH": "North",
        "Elum, WA": "Cle",
        "Falls, NY": "Niagara",
        "Francisco, CA": "San",
        "Grande, AZ": "Casa",
        "Green, KY": "Bowling",
        "Grove, IL": "Downers",
        "Guardia, NY": "La",
        "Harbor, NH": "Center",
        "Heights, IL": "Arlington",
        "Heights, NJ": "Hasbrouck",
        "Hills, CA": "Woodland",
        "Hill, NJ": "Cherry",
        "Hill, ON": "Richmond",
        "Island, NY": "Long",
        "Jose, CA": "San",
        "Juan, PR": "San",
        "Lac, WI": "Fond du",
        "Laoghaire, Ireland": "Dun",
        "Lake, OH": "Indian",
        "Lauderdale, FL": ["Fort", "Ft."],
        "Laurel, NJ": "Mt.",
        "Louis, MO": "St.",
        "Luzerne, NY": "Lake",
        "Malvern, UK": "Great",
        "Mateo, CA": "San",
        "Memphis, TN": "East",
        "Moines, IA": "Des",
        "Mountain, GA": "Pine",
        "Nuys, CA": "Van",
        "Oak, FL": "Live",
        "Orleans, LA": "New",
        "Park, AZ": "Litchfield",
        "Park, KS": "Overland",
        "Park, MD": ["Lexington", "College"],
        "Park, MN": ["St. Louis", "Brooklyn"],
        "Paso, TX": "El",
        "Pass, WA": "Snoqualmie",
        "Paul, MN": "St.",
        "Petersburg, FL": "St.",
        "Plainfield, NJ": "South",
        "Plains, NY": "White",
        "Point, NC": "High",
        "Raton, FL": "Boca",
        "Rock, AR": ["Little", "North Little"],
        "Rosa, CA": "Santa",
        "Sacramento, CA": "West",
        "Sheen, UK": "East",
        "Spring, MD": "Silver",
        "Springs, CO": "Colorado",
        "Springs, NY": "Saratoga",
        "Station, TX": "College",
        "Town, NY": "Rye",
        "Valley, MD": "Hunt",
        "Vegas, NV": "Las",
        "Vernon, WA": "Mount",
        "Way, WA": "Federal",
        "Worth, TX": ["Ft", "Ft."],
        "York, NY": "New"
    }

    # Look for a pattern of the form:
    #   in Word, XX
    #   where Word is one or more strings of letters each with an initial capital, the comma is optional, and XX is a pair of upper case letters
    # Note that this will also pick up roman-numeraled con names, E.g., Fantasycon XI, so we need to remove these later
    def ScanForLocales(self, s: str, pagename: str) -> List[Locale]:

        # Find the first locale
        # Detect locales of the form Name [Name..Name], XX  -- One or more capitalized words followed by an optional comma followed by exactly two UC characters
        # ([A-Z][a-z]+\]*,?\s)+     Picks up one or more leading capitalized, space (or comma)-separated words (we allow a '.' to handle things like "St. Paul")
        # \[*  and  \]*             Lets us ignore spans of [[brackets]]
        # The "[^a-zA-Z]"           Prohibits another letter immediately following the putative 2-UC state
        s1=s.replace("[", "").replace("]", "")  # Remove brackets
        m=re.search("in ([A-Z][a-z.]+\s+)?([A-Z][a-z.]+\s+)?([A-Z][a-z]+,?\s+)([A-Z]{2})[^a-zA-Z]",
                    " "+s1+" ")  # The added spaces are so that there is at least one character before and after any possible locale
        # Note: we only want to look at the first hit; later ones are far too likely to be accidents.
        if m is not None and len(m.groups()) > 1:
            groups=[x for x in m.groups() if x is not None]

            city=" ".join(groups[0:-1]) # It's assumed to be possible-multi-word-city state-country, where state-country is a single token
            city=city.replace(",", " ")  # Get rid of any commas after city
            city=re.sub("\s+", " ", city).strip()  # Multiple spaces go to single space and trim the result
            city=city.split()       # Split it back up into tokens

            state=groups[-1].strip()

            impossiblestates={"SF", "MC", "PR", "II", "IV", "VI", "IX", "XI", "XX", "VL", "XL", "LV",
                              "LX"}  # PR: Progress Report; others Roman numerals; "LI" is reluctantly allowed because of Long Island (maybe a mistake?)
            if state not in impossiblestates:
                # City should consist of a kist of one or more capitalized tokens.
                if len(city) > 0:
                    skippers={"Astra", "Con"}  # Second word of some multi-word con names
                    if city[-1] not in skippers:
                        # OK, now we know we have at least the form "in Xxxx[,] XX", but there may be many capitalized words before the Xxxx.
                        # If not -- if we have *exactly* "in Xxxx[,] XX" -- then we have a local (as best we can tell).  Return it.
                        loc=city[-1]+", "+state
                        if len(city) == 1:
                            if loc in self.locales.keys():
                                return [self.locales[loc]]
                            self.probableLocales.setdefault(loc, [])
                            self.probableLocales[loc].append(pagename)
                            Log(f"{loc} not in locales (1)")
                            return []
                        # Apparently we have more than one leading word.  Check the last word+state against the multiWordCities dictionary.
                        # If the multi-word city is found, we're good.
                        if loc in self.multiWordCities.keys():
                            # Check the preceding token in the name against the token in multiWordCities
                            tokens=self.multiWordCities[loc]
                            if type(tokens) == str:
                                if tokens == " ".join(city[:-1]):
                                    name=tokens+" "+loc
                                    if name in self.locales.keys():
                                        return [self.locales[name]]
                                    self.probableLocales.setdefault(name, [])
                                    self.probableLocales[name].append(pagename)
                                    Log(f"{name} not in locales (2)")
                                    return []
                            else:
                                # It's a list of strings
                                for token in tokens:
                                    if token == " ".join(city[:-1]):
                                        name=token+" "+loc
                                        if name in self.locales.keys():
                                            return [self.locales[name]]
                                        self.probableLocales.setdefault(name, [])
                                        self.probableLocales[name].append(pagename)
                                        Log(f"{name} not in locales (3)")
                                        return []

        # OK, we can't find the Xxxx, XX pattern
        # Look for 'in'+city+[,]+spelled-out-country
        # We'll look for a country name preceded by the word 'in' and one or two Capitalized words
        countries=["Australia", "Belgium", "Bulgaria", "Canada", "China", "England", "Germany", "Holland", "Ireland",
                   "Israel", "Italy", "New Zealand", "Netherlands", "Norway", "Sweden", "Finland", "Japan", "France",
                   "Poland", "Russia", "Scotland", "Wales"]
        out: List[Locale]=[]
        s1=s.replace("[", "").replace("]", "")  # Remove brackets
        splt=SplitOnSpan(",.\s", s1)  # Split on spans of comma, period, and space
        for country in countries:
            try:
                if country in splt:
                    loc=splt.index(country)     # Find the index of the country name in the list of tokens
                    if loc > 2:  # Minimum is 'in City, Country', so there must be at least two tokens
                        splt=splt[:loc]     # Drop the country and everything after it
                        locale=""
                        rest=""
                        sep=""
                        for i in range(len(splt)-1, max(len(splt)-7, 0), -1):  # City can be up to five tokens before we get to the country.  Match from shortest to longest.
                            if re.match("^[A-Z][a-z]+$", splt[i]):  # Look for Xxxxx
                                rest=splt[i]+sep+rest       # Build up the locale string by prepending the matched token
                                locale=rest+", "+country
                            if splt[i-1] == "in":
                                # OK, we've found a string of tokens: "in Xxxx Xxxx...Xxxx Country"
                                if locale in self.locales.keys():   # Is this local recognized?
                                    return [self.locales[locale]]
                                if country == "Australia" or country == "AU":
                                    # OK, some places have more complicated structures, e.g., Australia
                                    #       Perth, Western Australia
                                    #       Sydney NSW, Australia
                                    #       Sydney New South Wales, Australia
                                    # Create a list of "middle" phrases that point unambiguously to a city in Australia.  We can then just drop them
                                    aussies=["Australian Capital Territory", "Western", "NSW", "N.S.W.", "New South Wales", "Queensland", "South", "Victoria", "Vic", "ACT", "A.C.T."]
                                    for aus in aussies:
                                        if rest.endswith(aus):
                                            locale=rest[:-len(aus)].strip()+", "+country
                                            break
                                    if locale in self.locales.keys():   # Is this local recognized?
                                        return [self.locales[locale]]
                                self.probableLocales.setdefault(locale, [])
                                self.probableLocales[locale].append(pagename)
                                Log(f"{locale} not in locales (5)")
                                return []
                            sep=" "
            except ValueError:
                continue

        # Look for the pattern "in [[City Name]]"
        # This has the fault that it can find something like "....in [[John Campbell]]'s report" and think that "John Campbell" is a locale.
        # Fortunately, this will nearly always happen *after* the first sentence which contains the actual locale, and we ignore second and later hits
        # Pattern:
        # Capture "in" followed by "[[" followed by a group
        # The group is a possibly-repeated non-capturing group
        #       which is a UC letter followed by one or more letters followed by an optional period or comma followed by zero or more spaces
        # ending with "]]"
        lst=re.findall("in \[\[((?:[A-Z][A-Za-z]+[.,]?\s*)+)]]", s)
        if len(lst) > 0:
            if lst[0] in self.locales.keys():
                out.append(self.locales[LocaleHandling().BaseFormOfLocaleName(lst[0])])
            else:
                Log(f"{lst[0]} not in locales (4)")
                self.probableLocales.setdefault(lst[0], [])
                self.probableLocales[lst[0]].append(pagename)
        return out

