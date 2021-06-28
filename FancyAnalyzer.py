from __future__ import annotations
from typing import Dict, List, Tuple

import os
import re

from F3Page import F3Page, DigestPage, TagSet
from Log import Log, LogOpen
from HelpersPackage import WindowsFilenameToWikiPagename


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
#allFancy3PagesFnames= [f for f in allFancy3PagesFnames if f[0] in "A"]        # Just to cut down the number of pages for debugging purposes

excludedPrefixes=["_admin", "Template;colon", "User;colon"]
for prefix in excludedPrefixes:
    allFancy3PagesFnames = [f for f in allFancy3PagesFnames if not f.startswith(prefix)]     # Drop various tool, admin, etc., pages

excludedPages=["Admin", "Standards", "Test Templates"]
allFancy3PagesFnames=[f for f in allFancy3PagesFnames if f not in excludedPages]

Log("   "+str(len(allFancy3PagesFnames))+" pages found")

fancyPagesDictByWikiname: Dict[str, F3Page]={}     # Key is page's canname; Val is a FancyPage class containing all the references on the page

Log("***Scanning local copies of pages for links")
for pageFname in allFancy3PagesFnames:
    if pageFname.startswith("Log 2"):     # Ignore Log 2xxx files in the site directory
        continue
    val=DigestPage(fancySitePath, pageFname)
    if val is not None:
        fancyPagesDictByWikiname[val.Name]=val
Log("   "+str(len(fancyPagesDictByWikiname))+" semi-unique links found")


# OK, now we have a dictionary of all the pages on Fancy 3, which contains all of their outgoing links
# Build up a dictionary of redirects.  It is indexed by the canonical name of a page and the value is the canonical name of the ultimate redirect
# Build up an inverse list of all the pages that redirect *to* a given page, also indexed by the page's canonical name. The value here is a list of canonical names.
redirects: Dict[str, str]={}            # Key is the name of a redirect; value is the ultimate destination
inverseRedirects: Dict[str, List[str]]={}     # Key is the name of a destination page, value is a list of names of pages that redirect to it
for fancyPage in fancyPagesDictByWikiname.values():
    if fancyPage.Redirect is not None:
        if fancyPage.Redirect is not None:  # A page has an UltimateRedirect iff it has a Redirect
            assert fancyPage.UltimateRedirect is not None
        else:
            assert fancyPage.UltimateRedirect is None
        redirects[fancyPage.Name]=fancyPage.UltimateRedirect

        inverseRedirects.setdefault(fancyPage.Redirect, [])
        inverseRedirects[fancyPage.Redirect].append(fancyPage.Name)

        inverseRedirects.setdefault(fancyPage.UltimateRedirect, [])
        if fancyPage.UltimateRedirect != fancyPage.Redirect:
            inverseRedirects[fancyPage.UltimateRedirect].append(fancyPage.Name)

# Create a dictionary of page references for people pages.
# The key is a page's canonical name; the value is a list of pages at which they are referenced.

# First locate all the people and create empty entries for them
peopleReferences: Dict[str, List[str]]={}
Log("***Creating dict of people references")
for fancyPage in fancyPagesDictByWikiname.values():
    if fancyPage.IsPerson:
        peopleReferences.setdefault(fancyPage.Name, [])

# Now go through all outgoing references on the pages and add those which reference a person to that person's list
for fancyPage in fancyPagesDictByWikiname.values():
    if fancyPage.OutgoingReferences is not None:
        for outRef in fancyPage.OutgoingReferences:
            if outRef.LinkWikiName in peopleReferences.keys():    # So it's a people
                peopleReferences[outRef.LinkWikiName].append(fancyPage.Name)

Log("***Writing reports")
# Write out a file containing canonical names, each with a list of pages which refer to it.
# The format will be
#     **<canonical name>
#     <referring page>
#     <referring page>
#     ...
#     **<cannonical name>
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
allFancy3Pagenames=[WindowsFilenameToWikiPagename(n) for n in allFancy3PagesFnames]
with open("Redirects with missing target.txt", "w+", encoding='utf-8') as f:
    for key in redirects.keys():
        dest=redirects[key]
        if dest not in allFancy3Pagenames:
            f.write(key+" --> "+dest+"\n")


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
peopleNames=[]
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
                        peopleNames.append(RemoveTrailingParens(fancyPagesDictByWikiname[p].UltimateRedirect))
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
# Make a list of all fans, pros, and mundanes who are not also tagged person
Log("Writing: Fans, Pros, and mundanes who are not Persons.txt")
with open("Fans and Pros, and mundanes who are not Persons.txt", "w+", encoding='utf-8') as f:
    for fancyPage in fancyPagesDictByWikiname.values():
        # Then all the redirects to one of those pages.
        if ("Fan" in fancyPage.Tags or "Pro" in fancyPage.Tags or "Mundane" in fancyPage.Tags) and "Person" not in fancyPage.Tags:
            f.write(fancyPage.Name+": "+str(fancyPage.Tags)+"\n")


##################
# Make a list of persons who don't also have a specific tag
Log("Writing: Persons who are not Fans, Pros, or Mundanes.txt")
with open("Persons who are not Fans, Pros, or Mundanes.txt", "w+", encoding='utf-8') as f:
    for fancyPage in fancyPagesDictByWikiname.values():
        # Then all the redirects to one of those pages.
        if "Person" in fancyPage.Tags and "Fan" not in fancyPage.Tags and "Pro" not in fancyPage.Tags and "Mundane" not in fancyPage.Tags:
            f.write(fancyPage.Name+": "+str(fancyPage.Tags)+"\n")


##################
# Make a list of all Mundanes
Log("Writing: Mundanes.txt")
with open("Mundanes.txt", "w+", encoding='utf-8') as f:
    for fancyPage in fancyPagesDictByWikiname.values():
        # Then all the redirects to one of those pages.
        if "Mundane" in fancyPage.Tags:
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
                if "Fan" in fancyPage.Tags or "Pro" in fancyPage.Tags or "Person" in fancyPage.Tags:
                    npeople+=1
                if "Fan" in fancyPage.Tags:
                    nfans+=1
                if ("Fanzine" in fancyPage.Tags or "Apazine" in fancyPage.Tags or "Clubzine" in fancyPage.Tags or "Newszine" in fancyPage.Tags or "Fanthology" in fancyPage.Tags):
                    nfanzines+=1
                if "APA" in fancyPage.Tags:
                    napas+=1
                if "Club" in fancyPage.Tags:
                    nclubs+=1
                if "Convention" in fancyPage.Tags:
                    nconinstances+=1
    f.write("Unique (ignoring redirects)\n")
    f.write("  Total pages: " + str(npages) + "\n")
    f.write("  All people: " + str(npeople) + "\n")
    f.write("  Fans: " + str(nfans) + "\n")
    f.write("  Fanzines: "+str(nfanzines)+"\n")
    f.write("  APAs: " + str(napas) + "\n")
    f.write("  Clubs: " + str(nclubs) + "\n")
    f.write("  Conventions: " + str(nconinstances) + "\n")