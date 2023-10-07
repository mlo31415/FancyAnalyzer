from __future__ import annotations
from dataclasses import dataclass
from collections import defaultdict

import re

from F3Page import F3Page
from Log import LogSetHeader, Log
from HelpersPackage import SplitOnSpan, WikidotCanonicizeName, StripWikiBrackets, FindWikiBracketedText


############################################################################################
# This class encapsulates our knowledge of Locale pages

# There are four kinds of pages which generate a LocalePage:
#   A base Locale: typically a metropolitan name in standard form, e.g., Boston, MA).  It is tagged as a Locale and is not a redirect
#   A shortname: Some cities, e.g., Boston, London, New York, are usually referred to without state/country.
#   A non-base Locale: typically a location in a metro area, e.g., Cambridge, MA. It is tagged as a Locale, but redirects to a base Locale
#   A synonym: typically a variant spelling or Wikidot form of a base (or non-base) Locale, e.g., Cambridge_ma. It is a redirect to a Locale, but not tagged as one
# In addition, a local can be created for a non-page.  In this case only member NonPageName is set
@dataclass
class LocalePage:
    PageName: str=""        # The Fancy 3 page name of this LocalePage.
    DisplayName: str=""     # If there's a MediaWiki Displayname override, put it here. Otherwise empty string
    Redirect: str=""        # If this is a redirect page, the page name of the target. Otherwise empty string
    IsTaggedLocale: bool=False    # Is this page tagged "Locale"?
    NonPageName: str=""     # If this is a locale created with no associated page

    # Compare two Locales for equality. Ignore whether or not they are linked
    def __eq__(self, val: LocalePage) -> bool:
        # Compare two strings ignoring [[...]]
        def CompNoBrackets(s1: str, s2: str) -> bool:
            return StripWikiBrackets(s1) == StripWikiBrackets(s2)

        return CompNoBrackets(self.PageName, val.PageName) and \
            CompNoBrackets(self.DisplayName, val.DisplayName) and \
            CompNoBrackets(self.Redirect, val.Redirect) and \
            self.IsTaggedLocale == val.IsTaggedLocale and \
            CompNoBrackets(self.NonPageName, val.NonPageName)

    def __str__(self) -> str:
        if len(self.DisplayName) > 0:
            return self.DisplayName
        if len(self.PageName) > 0:
            return self.PageName
        if len(self.PageName) == 0 and len(self.DisplayName) == 0 and len(self.Redirect) == 0 and not self.IsTaggedLocale and len(self.NonPageName) == 0:
            return ""
        return f"LocalePage({self.PageName=}  {self.DisplayName=}  {self.Redirect=}  {self.IsTaggedLocale=}  {self.NonPageName=})"


    @property
    # Provides a formatted link to this LocalePage (or just the name if there is no associated page)
    def Link(self) -> str:
        if self.IsEmpty:
            return ""
        # If this is a non-page Locale, just return the undecorated locale name
        if len(self.NonPageName) > 0:
            return self.NonPageName
        # If this is tagged as a Locale and is a real page, we return a simple link to that page.
        # This will work for a regular page, a regular page with a displaytitle or a redirect
        if self.IsTaggedLocale:
            return "[["+self.PageName+"]]"
        # Otherwise, it must be a page which links to a Locale page, so we return a simple link to the page
        if self.IsRedirect:
            return "[["+self.PageName+"]]"
        # Oops
        return f"LocalePage.Link({self}) failure"

    @property
    def IsEmpty(self) -> bool:
        return len(self.PageName) == 0 and len(self.Redirect) == 0 and len(self.NonPageName) == 0

    @property
    def IsLocale(self) -> bool:
        return self.IsTaggedLocale

    @property
    def IsRedirect(self) -> bool:
        return len(self.Redirect) > 0

    @property
    # Is this nothing but a pointer for the Wikidot canonical name of the page?
    # Note that we can't detect a Wikidot redirect that is only a single lower case word
    def IsWikidotRedirect(self) -> bool:
        if not self.Redirect:
            return False
        #TODO Is there some way we can check on presence of Wikidot tag?
        return  not self.IsTaggedLocale and self.PageName == WikidotCanonicizeName(self.PageName) and "_" in self.PageName

    @property
    # Is this a page in the Fancy wiki?
    def IsPage(self) -> bool:
        return len(self.PageName) > 0

    @property
    def PreferredName(self) -> str:
        # If this is itself tagged as a Locale we return the page name even if it is also a redirect
        # E.g., we return "Cambridge, MA" because it is tagged Locale even though it points to "Boston, MA"
        if self.IsTaggedLocale:
            if len(self.DisplayName) > 0:
                return self.DisplayName
            return self.PageName

        # If all of the real page names are empty, we just return the NonPageName -- either it's real and we need to return it or it is also empty which is still correct
        if self.DisplayName == "" and self.PageName == "" and self.Redirect == "":
            return self.NonPageName

        # At this point we know it's a real page and not itself a locale.
        # If it's a Wikidot redirect, we always return the redirect
        if self.IsWikidotRedirect:  # Note that this test is not perfect, since it can't look at the page's contents.
            return self.Redirect

        # LocalePage or not, if it's a redirect, follow the redirect!
        if self.Redirect:
            return self.Redirect    #TODO: should go to redirect's LocalePage to see if it has some other preferred name?

        # Looks like an error
        Log(f"@@@LocalePage '{self.PageName}' is not tagged as Locale, but is not in Wikidot format either", Print=False, isError=True)
        if self.PageName != "":
            return self.PageName

        return ""



    #-------------------------------------------------------------
    # Compare two locations to see if they match
    def LocMatch(self, loc2: str) -> bool:

        # First, remove '[[' and ']]' from both locs
        loc1=self.PreferredName
        loc2=loc2.replace("[[", "").replace("]]", "")

        if loc1 == loc2:
            return True

        # If one is empty and the other not, it'a a non-match
        if loc1 == "" or loc2 == "":
            return False

        # if self redirects to loc 2 it's a match
        if self.Redirect != "" and self.Redirect == loc2:
            return True

        # If loc 2 redirects to self, it's a match,a lso.  (A bit more work to determine.)
        if loc2 not in LocaleHandling.locales.keys():
            return False
        locale2=LocaleHandling.locales[loc2]
        if locale2.Redirect != "" and locale2.Redirect == self.PageName:
            return True

        # Some names are special (e.g., Boston), wso we compare them in their reduced forms.
        if loc1 in LocaleHandling.specialNames.keys():
            loc1=LocaleHandling.specialNames[loc1]
        if loc2 in LocaleHandling.specialNames.keys():
            loc2=LocaleHandling.specialNames[loc2]
        return loc1 == loc2


############################################################################################
class LocaleDict:
    def __init__(self):
        self.d: dict[str, LocalePage]={}

    def __getitem__(self, i: str) -> LocalePage:
        if i not in self.d.keys():
            Log(f"LocaleDict({i}) does not exist")
            raise IndexError
        return self.d[i]

    def __setitem__(self, i: str, val: LocalePage) -> None:
        self.d[i]=val

    def __len__(self):
        return len(self.d)

    def values(self):
        return self.d.values()

    def keys(self):
        return self.d.keys()


############################################################################################
class LocaleHandling:
    # A set of the names of all LocalePages
    # We use a set to eliminate duplicates and to speed checks
    locales: LocaleDict=LocaleDict()

    # We also identify some things as probable locales which are not tagged directly or indirectly as locales
    # Maintain a dict of lists of pages that contain them
    probableLocales: dict[str, list[str]]=defaultdict(list)

    # This will be a pointer to fancyPagesDictByWikiname
    allPages: dict[str, F3Page]={}

    # Go through the entire set of pages looking for locales and harvest the information to create the list of all locales
    def Create(self, fancyPagesDictByWikiname: dict[str, F3Page]) -> None:
        LocaleHandling.allPages=fancyPagesDictByWikiname
        for page in LocaleHandling.allPages.values():
            # Add locale pages to the set
            if page.IsLocale:
                LogSetHeader("Found LocalePage "+page.Name)
                self.locales[page.Name]=LocalePage(PageName=page.Name, Redirect=page.Redirect, IsTaggedLocale=page.IsLocale, DisplayName=page.DisplayTitle)
            else:
                # If this page is a redirect to a locale page, add this page to the locale set
                # TODO: Do we want all redirects to locale pages or just those tagged as a locale?
                if page.IsRedirectpage and page.Redirect in LocaleHandling.allPages.keys() and LocaleHandling.allPages[page.Redirect].IsLocale:
                    LogSetHeader("Processing LocalePage redirect "+page.Name)
                    self.locales[page.Name]=LocalePage(PageName=page.Name, Redirect=page.Redirect, IsTaggedLocale=page.IsLocale, DisplayName=page.DisplayTitle)

    # key is full name, value is preferred name
    # Generally these will only be major (in both the fannish and mundane sense) cities.
    specialNames: dict[str, str]={
        "Boston, MA": "Boston",
        "Chicago, IL": "Chicago",
        "Dublin, IE": "Dublin",
        "Glasgow, UK": "Glasgow",
        "LA": "Los Angeles",
        "London, UK": "London",
        "Los Angeles, CA": "Los Angeles",
        "Melbourne, Australia": "Melbourne",
        "New York, NY": "New York",
        "New York City": "New York",
        "Philadelphia, PA": "Philadelphia",
        "San Francisco, CA": "San Francisco",
        "Sydney, Australia": "Sydney"
    }

    # Return the preferred form of a locale.  This may be City+State or City+Country or just City
    #       "Cambridge_ma" -> "Cambridge, MA"
    #       "Boston" -> "Boston, MA"
    #       "London, UK" --> "London"
    def BaseFormOfLocaleName(self, name: str) -> str:
        if name not in self.locales.keys():
            Log(f"BaseFormOfLocaleName({str}) failed")
            return ""
        locale=self.locales[name]
        if not locale.IsLocale and locale.IsRedirect:
            locale=self.locales[locale.Redirect]
        name=locale.PreferredName

        if name in self.specialNames.keys():
            return self.specialNames[name]

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
        "Rapids, IA": "Cedar",
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


    def AppendLocale(self, rslts: list[str], pagename: str) -> list[LocalePage]:
        out=[]
        if len(rslts) > 0:
            for rslt in rslts:
                if rslt in LocaleHandling.allPages.keys():
                    page=LocaleHandling.allPages[rslt]
                    out.append(LocalePage(PageName=page.Name, Redirect=page.Redirect, IsTaggedLocale=page.IsLocale, DisplayName=page.DisplayTitle))
                else:
                    out.append(LocalePage(NonPageName=rslt))
                    self.probableLocales[rslt].append(pagename)
        return out

    # Look for a pattern of the form:
    #   in Word, XX
    #   where Word is one or more strings of letters each with an initial capital, the comma is optional, and XX is a pair of upper case letters
    # Note that this will also pick up roman-numeraled con names, E.g., Fantasycon XI, so we need to remove these later
    def ScanConPageforLocale(self, s: str, pagename: str) -> list[LocalePage]:

        # Find the first locale
        # Detect locales of the form Name [Name..Name], XX  -- One or more capitalized words followed by an optional comma followed by exactly two UC characters
        # ([A-Z][a-z\-]+\]*,?\s)+     Picks up one or more leading capitalized, space (or comma)-separated words (we allow a '.' to handle things like "St. Paul")
        # \[*  and  \]*             Lets us ignore spans of [[brackets]]
        # The "[^a-zéA-Z]"           Prohibits another letter immediately following the putative 2-UC state
        out: list[LocalePage]=[]
        found=False
        s1=s.replace("[", "").replace("]", "")  # Remove brackets
        m1=re.search("[^A-Za-zé]in [A-Z][a-zé.,]+\s+", s1)  # Search for the word "in" followed by an upper-case word.  This may be the start of ...in City, State...
        # Note: we only want to look at the first hit; later ones are far too likely to be accidents.
        if m1 is not None:
            s1=s1[m1.span()[0]+3:]      # Drop the "in" token
            rslts=self.ScanForCityST(s1, pagename)
            if len(rslts) > 0:
                found=True
                out.extend(self.AppendLocale(rslts, pagename))

        if not found:
            m2=re.search("[^A-Za-zé]in \[\[[A-Z][a-zé.,]+", s)  # Search for the word "in" followed by '[[' and then an upper-case word.  This may be the start of ...in [[City, Country]]...
            # Note: we only want to look at the first hit; later ones are far too likely to be accidents.
            if m2 is not None:
                s2=s[m2.span()[0]+1:]  # Drop the "in" token
                rslts=self.ScanForCityCountry(s2)
                if len(rslts) > 0:
                    found=True
                    out.extend(self.AppendLocale(rslts, pagename))

        if not found and m1 is not None:
            # Now scan for a stand-alone City name
            rslts=self.ScanForCity(s1)
            if len(rslts) > 0:
                found=True
                out.extend(self.AppendLocale(rslts, pagename))

        if not found and m2 is not None:
            rslts=self.ScanForCity(s2)
            if len(rslts) > 0:
                out.extend(self.AppendLocale(rslts, pagename))

        return out

    # We have text which is supposedly a locale: Try to interpret it
    def ScanForLocale(self, s: str, pagename: str) -> list[LocalePage]:

        # Find the first locale
        # Detect locales of the form Name [Name..Name], XX  -- One or more capitalized words followed by an optional comma followed by exactly two UC characters
        # ([A-Z][a-zé]+\]*,?\s)+     Picks up one or more leading capitalized, space (or comma)-separated words (we allow a '.' to handle things like "St. Paul")
        # \[*  and  \]*             Lets us ignore spans of [[brackets]]
        # The "[^a-zéA-Z]"           Prohibits another letter immediately following the putative 2-UC state
        out: list[LocalePage]=[]
        found=False
        s1=s.replace("[", "").replace("]", "")  # Remove brackets
        m1=re.search("[A-Z][a-zé,]+\s+", s1)  # Search for an upper-case word.  This may be the start of ...in City, State...
        # Note: we only want to look at the first hit; later ones are far too likely to be accidents.
        if m1 is not None:
            rslts=self.ScanForCityST(s1, pagename)
            if len(rslts) > 0:
                found=True
                out.extend(self.AppendLocale(rslts, pagename))

        if not found:
            m2=re.search("\[\[[A-Z][a-zé.,-]+", s)  # Search for '[[' and then an upper-case word.  This may be the start of ...in [[City, Country]]...
            # Note: we only want to look at the first hit; later ones are far too likely to be accidents.
            if m2 is not None:
                rslts=self.ScanForCityCountry(s)
                if len(rslts) > 0:
                    found=True
                    out.extend(self.AppendLocale(rslts, pagename))

        if not found and m1 is not None:
            # Now scan for a stand-alone City name
            rslts=self.ScanForCity(s1)
            if len(rslts) > 0:
                found=True
                out.extend(self.AppendLocale(rslts, pagename))

#        if not found and m2 is not None:
        if not found:
            rslts=self.ScanForCity(s)
            if len(rslts) > 0:
                out.extend(self.AppendLocale(rslts, pagename))

        return out


    def ScanForCityST(self, s: str, pagename: str) -> list[str]:

        # Find the first locale
        # Detect locales of the form Name [Name..Name], XX  -- One or more capitalized words followed by an optional comma followed by exactly two UC characters
        # ([A-Z][a-zé]+\]*,?\s)+     Picks up one or more leading capitalized, space (or comma)-separated words (we allow a '-' to handle things like "Port-Royal")
        # \[*  and  \]*             Lets us ignore spans of [[brackets]]
        # The "[^a-zéA-Z]"           Prohibits another letter immediately following the putative 2-UC state
        s1=s.replace("[", "").replace("]", "")  # Remove brackets
        m=re.search("([A-Z][a-zé-]+\s+)?([A-Z][a-zé-]+\s+)?([A-Z][a-zé-]+,?\s+)([A-Z]{2})[^a-zéA-Z]", " "+s1+" ")  # The added spaces are so that there is at least one character before and after any possible locale
        # Note: we only want to look at the first hit; later ones are far too likely to be accidents.
        if m is not None and len(m.groups()) > 1:
            groups=[x for x in m.groups() if x is not None]

            city=" ".join(groups[0:-1]) # It's assumed to be possible-multi-word-city state-country, where state-country is a single token
            city=city.replace(",", " ")  # Get rid of any commas after city
            city=re.sub("\s+", " ", city).strip()  # Multiple spaces go to single space and trim the result
            city=city.split()       # Split it back up into tokens

            state=groups[-1].strip()

            impossiblestates={"SF", "MC", "PR", "II", "IV", "VI", "IX", "XI", "XX", "VL", "XL", "LV", "LX"}  # PR: Progress Report; others Roman numerals; "LI" is reluctantly allowed because of Long Island (maybe a mistake?)
            if state not in impossiblestates:
                # City should consist of a list of one or more capitalized tokens.
                if len(city) > 0:
                    skippers={"Astra", "Con"}  # Second word of some multi-word con names
                    if city[-1] not in skippers:
                        # OK, now we know we have at least the form "in Xxxx[,] XX", but there may be many capitalized words before the Xxxx.
                        # If not -- if we have *exactly* "in Xxxx[,] XX" -- then we have a local (as best we can tell).  Return it.
                        loc=city[-1]+", "+state
                        if len(city) == 1:
                            if loc not in self.locales.keys():
                                self.probableLocales[loc].append(pagename)
                            return [loc]

                        # Apparently we have more than one leading word.  Check the last word+state against the multiWordCities dictionary.
                        # If the multi-word city is found, we're good.
                        if loc in self.multiWordCities.keys():
                            # Check the preceding token in the name against the token in multiWordCities
                            tokens=self.multiWordCities[loc]
                            if type(tokens) == str:
                                if tokens == " ".join(city[:-1]):
                                    name=tokens+" "+loc
                                    if name not in self.locales.keys():
                                        self.probableLocales[name].append(pagename)
                                    return [name]
                            else:
                                # It's a list of strings
                                for token in tokens:
                                    if token == " ".join(city[:-1]):
                                        name=token+" "+loc
                                        if name not in self.locales.keys():
                                            self.probableLocales[name].append(pagename)
                                        return [name]
        return []


    def ScanForCityCountry(self, s: str) -> list[str]:
        # OK, we can't find the Xxxx, XX pattern
        # Look for 'in'+city+[,]+spelled-out-country
        # We'll look for a country name preceded by the word 'in' and one or two Capitalized words
        #countries=defaultdict(lambda: None)
        # Note that this does not work for two-word country names, e.g., New Zealand
        # What I'm building here is a fast lookup for country names that can beapplied to a whole list in a comprehension.
        # countries=defaultdict(lambda: None)
        # # Note that this does not work for two-word country names, e.g., New Zealand
        # countries.update({"Australia":"Australia", "Belgium":"Belgium", "Bulgaria":"Bulgaria", "Canada":"Canada", "China":"China",
        #                   "England":"England", "Germany":"Germany", "Holland":"Holland", "Ireland":"Ireland",
        #                   "Israel":"Israel", "Italy":"Italy", "Netherlands":"Netherlands", "Norway":"Norway",
        #                   "Sweden":"Sweden", "Finland":"Finland", "Japan":"Japan", "France":"France",
        #                   "Poland":"Poland", "Russia":"Russia", "Scotland":"Scotland", "Wales":"Wales",
        #                   "New Zealand": "New Zealand", "Zealand": "Zealand"})
        # # countries=["Australia", "Belgium", "Bulgaria", "Canada", "China", "England", "Germany", "Holland", "Ireland",
        # #            "Israel", "Italy", "New Zealand", "Netherlands", "Norway", "Sweden", "Finland", "Japan", "France",
        # #            "Poland", "Russia", "Scotland", "Wales"]
        # s1=s.replace("[", "").replace("]", "")  # Remove all brackets
        # splt=SplitOnSpan(",.\s", s1)  # Split on spans of comma, period, and space which should leave a list of word tokens
        # countriesfound=[countries[x] for x in splt]
        # countriesfound=[x for x in countriesfound if x is not None]

        countries={"Australia", "Belgium", "Bulgaria", "Canada", "China", "England", "Germany", "Holland", "Ireland",
                   "Israel", "Italy", "Netherlands", "Norway", "Sweden", "Finland", "Japan", "France",
                   "Poland", "Russia", "Scotland", "Wales", "New Zealand", "Zealand"}
        s1=s.replace("[", "").replace("]", "")  # Remove all brackets
        splt=SplitOnSpan(",.\s", s1)  # Split on spans of comma, period, and space which should leave a list of word tokens
        countriesfound=[x for x in splt if x in countries]

        if len(countriesfound) == 0:
            return []

        out: list[str]=[]
        for country in countriesfound:

            # Deal with some two word countries.
            # Note that some are states which look like countries
            if country == "Australia":
                loc=splt.index(country)
                # South Australia and Western Australia --> Australia (This is OK since the only cities with cons are unique.)
                if loc > 0 and splt[loc-1] == "South":
                    del splt[loc-1]
                if loc > 0 and splt[loc-1] == "Western":
                    del splt[loc-1]
            elif country == "Zealand":
                loc=splt.index(country)
                if loc > 0 and splt[loc-1] == "New":
                    # Here we fudge "new Zealand" into being treated as one word
                    splt=splt[:loc-1]+["New Zealand"]+splt[loc+1:]
                    country="New Zealand"


            loc=splt.index(country)     # Find the index of the country name in the list of tokens
            if loc > 2:  # Minimum is 'in City, Country', so there must be at least two tokens
                start=splt[:loc]     # Drop the country and everything after it
                localetext=""
                rest=""
                sep=""
                for i in range(len(start)-1, max(len(start)-7, 0), -1):  # City can be up to five tokens before we get to the country.  Match from shortest to longest.
                # City can be up to five tokens before we get to the country.  Match from shortest to longest.
                    if re.match("^[A-Z][a-zé-]+$", start[i]):  # Look for Xxxxx
                        locale=rest+", "+country
                        localetext=rest+", "+country
                    if start[i-1] == "in":
                        if locale in self.locales.keys():   # Is this locale recognized?
                            return [locale]
                        if localetext in self.locales.keys():   # Is this possible locale recognized?
                            return [localetext]
                        if country == "Australia" or country == "AU":
                            # Some places have more complicated structures, e.g., Australia
                            #       Perth, Western Australia
                            #       Sydney NSW, Australia
                            #       Sydney New South Wales, Australia
                            # Create a list of "middle" phrases that point unambiguously to a city in Australia.  We can then just drop them
                            aussies=["Australian Capital Territory", "Western", "NSW", "N.S.W.", "New South Wales", "Queensland", "South",
                                     "Victoria", "Vic", "ACT", "A.C.T.", "Tasmania"]
                            for aus in aussies:
                                if rest.endswith(aus):
                                    localetext=rest[:-len(aus)].strip()+", "+country
                                    break
                            if localetext in self.locales.keys():   # Is this possible locale recognized?
                                return [localetext]
                        Log(f"{localetext} not in locales (5)")
                        Log(f"       line={s}")
                        return []
                    sep=" "
        return out


    def ScanForCity(self, s: str) -> list[str]:
        # Look for the pattern "[[One Or More Uppercase Names]]"
        # Pattern:
        # optional [[
        # One or more
            # Non-capturing group:
                # Uppercaseletter followed by
                # one or more letters
                # possibly followed by [.,]
                # followed by one or more spaces
        # ending with an optional "]]"

        # We special-case names like "St. Paul" and "Ft. Bragg" because in general we want to terminate city names on "."
        lst=re.findall("(?:\[\[)?([SF]t\.\s+(?:[A-Z][A-Za-zé]+,?\s*)+)(?:]])?", s)
        # We return either the first match if there is one or an empty string
        if len(lst) > 0:
            return [lst[0]]

        lst=re.findall("(?:\[\[)?((?:[A-Z][A-Za-zé-]+,?\s*)+)(?:]])?", s)
        # We return either the first match if there is one or an empty string
        if len(lst) > 0:
            return [lst[0]]
        return []


    #-------------------------------------------------------
    def LocaleFromName(self, pagename: str) -> LocalePage:
        if pagename not in LocaleHandling.locales.keys():
            return LocalePage()
        return LocaleHandling.locales[pagename]
