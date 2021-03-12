# Where the Spacy code was adapted from: https://spacy.io/usage/linguistic-features

from recipeScraper import openSession, formulateJSON
from youtube_search import YoutubeSearch
import spacy
import sys
import re
import nltk
import requests
import json

class RecipeBot:
    recipeData = None # All scraped data gets stored in this
    name = "Recipe Guide" # Name of the bot

    # All the recipe data gets parsed into predicates, which end up in these dicts
    ingPredicates = dict()
    instPredicates = dict()

    # Below is needed by the Spacy dependency parser
    nlp = spacy.load("en_core_web_sm")

    # Now for some commands and questions we can give the bot:
    botCommands = {"start": ["begin", "walk me through", "start", "want to make", "want to cook", "want to bake"],
    "nav": ["forward", "next", "back", "previous"],
    "questions": ["ingredients", "how do", "repeat", "how much"]}

    # This set of all possible foods helps with parsing
    allFoods = set(["tofu", "beef", "chicken", "pork", "pepperoni", "sausage", "turkey",
    "steak", "fish", "salmon", "shrimp", "lobster", "salami", "rennet", "poultry", "ham",
    "bacon", "lamb", "stock", "broth", "sauce", "loin", "tenderloin", "sirloin", "breast",
    "soy sauce", "milk", "cheese", "cream", "yogurt", "butter", "ghee", "coconut oil",
    "seasoning", "oregano", "salt", "oil", "onions", "onion"]) # Part of this list was constructed by referring to https://www.heart.org/en/healthy-living/healthy-eating/eat-smart/nutrition-basics/meat-poultry-and-fish-picking-healthy-proteins

    pairedWords = ["stock", "broth", "sauce", "loin", "tenderloin", "sirloin", "breast"] # Some food terms come paired with others and take a little extra processing
    cookingVerbs = ["place"] # ConceptNet can be very bad at detecting what things are verbs

    queryOffset = 100 # Number of results returned by ConceptNet API call

    ############################################################################
    # Name: __init__                                                           #
    # Params: None                                                             #
    # Returns: None                                                            #
    # Notes: Makes a HTTP request to get the right information about the       #
    # recipe and format it into a JSON.                                        #
    ############################################################################
    def __init__(self):
        userRecipeURL = input("\nHello and welcome to the " + self.name + "! If you are ready, go ahead and type in a URL that points to a recipe you would like to work on: ")
        request = openSession(userRecipeURL.strip())
        self.recipeData = formulateJSON(request)

    ############################################################################
    # Name: _ingParse                                                          #
    # Params: None                                                             #
    # Returns: None                                                            #
    # Notes: Using the recipe data store in self.recipeData, this parses out   #
    # the relevant portions (ingredient name, quantity, and measurement units) #
    # from the recipe data and saves these in the self.ingPredicates dict.     #
    # By predicate, we mean something like "(isa beef ingredient)", but to be  #
    # Pythonic, this is in a dict structure                                    #
    # (ex. self.ingPredicates["beef"]["isa"] = "beef").                        #
    # The parsing combines using a dependency parser and conceptNet to narrow  #
    # the "isa" predicate to point to a food. Oddly enough, whether the root   #
    # is an actual food can be separate from the often correct quantity and    #
    # measurement parsing.                                                     #
    ############################################################################
    def _ingParse(self):
        for i in range(len(self.recipeData["ingredients"])): # So we can distinguish between different ingredients with the same root
            ing = self.recipeData["ingredients"][i]
            parsedText = self.nlp(ing)
            additionalRoot = False # Turns true if the potential for a second root word pops up; semaphore to avoid storing that root word
            mainToken = None # The actual ingredient name
            for token in parsedText: # Construct the appropriate predicates
                if token.dep_ == "ROOT" and not additionalRoot: # Now we can traverse the parse tree
                    additionalRoot = True

                    # Now let's check if the root word is actually food
                    if self._isAFood(token.text.lower()):
                        mainToken = token.text
                    else: # If this fails, check every word in the sentence for food
                        for newToken in parsedText:
                            if self._isAFood(newToken.text.lower()):
                                mainToken = newToken.text
                                break # No need to keep going if we've got a food, as what came before the first food term was likely adjectives

                    # Sometimes, you get None for odd reasons. Seems better to go with what we have rather than adding an obscure layer of parsing.
                    # That said, there is one last check after this
                    if mainToken is None:
                        mainToken = token.text

                    # If you get beef sirloin, pork loin/tenderloin, or a kind of stock or broth,
                    # replace both words (e.g. chicken broth), not just "sirloin" or "broth"
                    if mainToken in self.pairedWords:
                        parsedTextAsList = list(parsedText)
                        mainToken = parsedTextAsList[parsedTextAsList.index(token) - 1].text + " " + token.text

                    # Now assign values based on the ingredient name
                    dictKey = mainToken + " " + str(i) # This is the key with which all info for this ingredient can be retrieved
                    self.ingPredicates[dictKey] = dict()
                    self.ingPredicates[dictKey]["isa"] = mainToken
                    for child in token.children: # Only related words are considered to be useful
                        requestObj = requests.get("http://api.conceptnet.io/c/en/" + child.text.lower() + "_" + mainToken.lower() + "?offset=0&limit=" + str(self.queryOffset)).json()

                        for edge in requestObj["edges"]: # Check if there are two word phrases like ground beef, so we can make a note of the entire phrase
                            eachEdge = edge["@id"].split(",") # Look for child.text + " " + token.text isa food
                            if "isa" in eachEdge[0].lower() and "/" + child.text.lower() + "_" + mainToken.lower() + "/" in eachEdge[1].lower() and "food" in eachEdge[2].lower():
                                self.ingPredicates[dictKey]["isa"] = child.text + " " + mainToken
                                ing = ing.replace(child.text + " " + mainToken, "isa")
                        if any([x.text.isdigit() for x in child.children]): # The measurement and amount, tied together by the parser
                            for item in child.children:
                                if item.text.isdigit():
                                    self.ingPredicates[dictKey]["quantity"] = item.text
                                    self.ingPredicates[dictKey]["measurement"] = child.text
                    self.ingPredicates[dictKey]["sentence"] = ing

    ############################################################################
    # Name: _isAFood                                                           #
    # Params: candidate (this is the thing that you are determining is a food  #
    # or not)                                                                  #
    # Returns: Boolean                                                         #
    # Notes: Leverage ConceptNet to see if candidate is a food. Since          #
    # ConceptNet is not particularly reliable, we also made use of our         #
    # allFoods set (which was built in __init__). We also collect spices for   #
    # the transformation to another cuisine.                                   #
    ############################################################################
    def _isAFood(self, candidate):
        requestJSON = requests.get("http://api.conceptnet.io/c/en/" + candidate + "?offset=0&limit=" + str(self.queryOffset)).json()
        finalVerdict = False # Is the ingredient a food or not
        if candidate in self.allFoods: # First check against our set of foods
            finalVerdict = True
        else: # If it's not there, then see if ConceptNet calls it a food
            for edge in requestJSON["edges"]:
                eachEdge = edge["@id"].split(",")
                if "isa" in eachEdge[0].lower() and "/" + candidate.lower() + "/" in eachEdge[1].lower() and "/food" in eachEdge[2].lower():
                    finalVerdict = True
        return finalVerdict

    ############################################################################
    # Name: _instParse                                                         #
    # Params: None                                                             #
    # Returns: None                                                            #
    # Notes: Using the recipe data store in self.recipeData, this parses out   #
    # the relevant portions (primary method and associated tool). We again     #
    # parse into predicates like before. The thing is we needed ConceptNet a   #
    # lot more here. Parsing instructions seems a lot more difficult than      #
    # parsing ingredients.                                                     #
    ############################################################################
    def _instParse(self):
        for i in range(len(self.recipeData["instructions"])):
            inst = self.recipeData["instructions"][i]
            parsedText = self.nlp(inst)
            additionalRoot = False # Turns true if the potential for a second root word pops up; semaphore to avoid storing that root word
            mainToken = None # This is the root word that turns into the primary method
            for token in parsedText:
                if token.dep_ == "ROOT" and not additionalRoot: # If you have multiple root words, go with the first one
                    additionalRoot = True # So we don't end up checking more root words - the first one (reading left-to-right) is usually what you want

                    if self._isAnAction(token.text): # Now let's check if the root word is actually a verb
                        mainToken = token.text
                    else: # If the above fails, check every word in the sentence for the first verb that is an action
                        for newToken in parsedText:
                            if self._isAnAction(newToken.text) and mainToken is None:
                                mainToken = newToken.text

                    # Sometimes, you get None for odd reasons. Seems better to go with what we have rather than adding an obscure layer of parsing
                    if mainToken is None:
                        mainToken = token.text

                    # Now we can assign the primary method and get a cooking tool for it
                    self.instPredicates[i] = dict()
                    self.instPredicates[i]["primaryMethod"] = mainToken
                    for child in token.children: # Now we start relying on ConceptNet to check if any of these children are cooking tools
                        requestObj = requests.get("http://api.conceptnet.io/c/en/" + child.text + "?offset=0&limit=" + str(self.queryOffset)).json()
                        for edge in requestObj["edges"]:
                            if "usedfor" in edge["@id"].lower() and edge["end"]["label"].lower() == "cook":
                                self.instPredicates[i]["toolFor"] = child.text
                    self.instPredicates[i]["sentence"] = inst

    ############################################################################
    # Name: _isAnAction                                                        #
    # Params: candidate (this is the thing that you are determining is a verb).#
    # Returns: Boolean                                                         #
    # Notes: Similar to _isAFood. This is just for the primaryMethod and       #
    # checks for verbs.                                                        #
    ############################################################################
    def _isAnAction(self, candidate):
        requestJSON = requests.get("http://api.conceptnet.io/c/en/" + candidate.lower() + "?offset=0&limit=" + str(self.queryOffset)).json()
        if candidate.lower() in self.cookingVerbs: # Since ConceptNet can be bad at detecting what is a verb
            return True
        else:
            for edge in requestJSON["edges"]:
                eachEdge = edge["@id"].split(",") # Check if this word is ever used as a verb
                if "mannerof" in eachEdge[0].lower() and ("/" + candidate.lower() + "/v/" in eachEdge[1].lower() or \
                "/" + candidate.lower() + "/v/" in eachEdge[2].lower()): # If the found root word is a verb
                    return True
        return False


    ############################################################################
    # Name: _processCommand                                                    #
    # Params: None                                                             #
    # Returns: userDecision (what the user wants to do next).                  #
    # Notes: Asks and waits until the user gives a valid input.                #
    ############################################################################
    def _processCommand(self, prompt, validPrompts):
        userDecision = input(prompt)

        while userDecision not in validPrompts:
            userDecision = int(input("\nI'm sorry, but your command could not be processed. Try again, and if there were numerical prompts, enter just the number: "))

        return userDecision

    ############################################################################
    # Name: _ingredientList                                                    #
    # Params: None                                                             #
    # Returns: userDecision (what the user wants to do next).                  #
    # Notes: Prints out the ingredient list and asks about what's next.        #
    ############################################################################
    def _ingredientList(self):
        print("\nSure, the ingredients are listed below: ")
        for ingKeys in self.ingPredicates.keys():
            print("- " + self.ingPredicates[ingKeys]["sentence"])

        # Now for what's next
        givenCommand = int(self._processCommand("\nWould you like me to move on to the first step (1) or repeat the list (2)? Enter your choice here: ",
        ["1", "2"]))

        # Go to the right place depending on the request
        if givenCommand == 1:
            self._instructionNavigation(0)
        elif givenCommand == 2:
            self._ingredientList()
        else: # Just a placeholder that will never be reached, hopefully, but just in case...
            print("\nI'm sorry, something went really wrong. You should not have reached this branch. The system will exit on its own.")
            sys.exit(0)

    ############################################################################
    # Name: _instructionNavigation                                             #
    # Params: currentStep (the step that the user is currently on,             #
    # zero-indexed), printInstAgain (tells the script whether to re-print the  #
    # instruction).                                                            #
    # Returns: None                                                            #
    # Notes: Helps the user navigate through instructions and handles anything #
    # anything that requires an external resource (Google, YouTube, etc.).     #
    ############################################################################
    def _instructionNavigation(self, currentStep, printInstAgain = True):
        if len(self.recipeData["instructions"]) == currentStep : # If the current step goes past the last possible instruction number, then we are done
            print("\nLooks like you're all done! Good work and enjoy your food! Thanks for using " + self.name + " and see you next time!")
            return
        else:
            for key in self.instPredicates.keys():
                instOfInterest = self.instPredicates[key]
                if key == currentStep: # If this is the instruction we are dealing with
                    if printInstAgain: # Check if we need to print this again (False if this was recursed on by an external resource command)
                        if currentStep == 0:
                            print("\nThe 1st step is: " + instOfInterest["sentence"])
                        elif currentStep == 1:
                            print("\nThe 2nd step is: " + instOfInterest["sentence"])
                        elif currentStep == 2:
                            print("\nThe 3rd step is: " + instOfInterest["sentence"])
                        else:
                            print("\nThe " + str(key + 1) + "th step is: " + instOfInterest["sentence"])

                    givenCommand = int(self._processCommand("\nWhat would you like to do next? \
                    [1] Repeat the instruction.\n \
                    [2] How to do that?\n \
                    [3] How do I do that thing?\n \
                    [4] Move on to the next instruction.\n Enter here: ", ["1", "2", "3", "4"])) # That = the primary method used in the instruction

                    if givenCommand == 1:
                        self._instructionNavigation(currentStep)
                    elif givenCommand == 2:
                        searchRes = json.loads(YoutubeSearch(instOfInterest["primaryMethod"], max_results=1).to_json())["videos"][0] # Get the search result
                        print("\nThere's a YouTube video that may be of some help. Check this out: " + \
                        "https://www.youtube.com" + searchRes["url_suffix"])
                        self._instructionNavigation(currentStep, printInstAgain = False)
                    elif givenCommand == 3:
                        action = input("\nWhich thing would you happen to be talking about? Enter here: ")
                        searchRes = json.loads(YoutubeSearch(action, max_results=1).to_json())["videos"][0] # Get the search result
                        print("\nThere's a YouTube video that may be of some help. Check this out: " + \
                        "https://www.youtube.com" + searchRes["url_suffix"])
                        self._instructionNavigation(currentStep, printInstAgain = False)
                    elif givenCommand == 4:
                        self._instructionNavigation(currentStep + 1)
                    else: # Just a placeholder that will never be reached, hopefully, but just in case...
                        print("\nI'm sorry, something went really wrong. You should not have reached this branch. The system will exit on its own.")
                        sys.exit(0)

    ############################################################################
    # Name: _allParsing                                                        #
    # Params: None                                                             #
    # Returns: None                                                            #
    # Notes: Any and all parsing methods to be called go here.                 #
    ############################################################################
    def _allParsing(self):
        newTransformer._ingParse()
        newTransformer._instParse()

    ############################################################################
    # Name: converse                                                           #
    # Params: None                                                             #
    # Returns: None                                                            #
    # Notes: This is really the entire spindle (i.e. function that ties        #
    # everything together). While it handles the highest level of the          #
    # conversation, the rest gets delegated to the methods above.              #
    ############################################################################
    def converse(self):
        self._allParsing() # This just pushes the parsing to another method in the name of modularity

        # Now we give the user a heads-up that it is time to begin
        # First tell the user what's going on:
        print("\n Thanks so much for your patience! We'll be working with " + self.recipeData["recipeName"] + ".")

        # Now ask them what they want to do next (i.e. ingredients or the first step?)
        givenCommand = int(self._processCommand("Where would you like to start? [1] Show the ingredient list.\n[2] Go to the first step. Enter here: ", ["1", "2"]))

        # Go to the right place depending on the request
        if givenCommand == 1:
            self._ingredientList()
        elif givenCommand == 2:
            self._instructionNavigation(0)
        else: # Just a placeholder that will never be reached, hopefully, but just in case...
            print("\nI'm sorry, something went really wrong. You should not have reached this branch. The system will exit on its own.")
            sys.exit(0)

if __name__ == "__main__":
    newTransformer = RecipeBot()
    print("\nThank you! This conversation will continue momentarily, but some things need to be readied first. This could take a little while.")
    newTransformer.converse()
