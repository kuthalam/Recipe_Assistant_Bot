# Where the Spacy code was adapted from: https://spacy.io/usage/linguistic-features

from recipeScraper import openSession, formulateJSON
from youtube_search import YoutubeSearch
from googlesearch import search
from nltk.metrics.distance import edit_distance
import spacy
import sys
import re
import requests
import json
import random

class RecipeBot:
    recipeData = None # All scraped data gets stored in this
    name = "Sous-chef" # Name of the bot

    # All the recipe data gets parsed into predicates, which end up in these dicts
    ingPredicates = dict()
    instPredicates = dict()

    # Below is needed by the Spacy dependency parser
    nlp = spacy.load("en_core_web_sm")

    # Now for some commands and questions we can give the bot:
    botCommandTypes = {"navTypes": ["forwardNav", "backwardNav", "otherNav", "beginningNav", "endingNav", "doneNav"]}
    botCommands = {"forwardNav": ["forward", "next", "after"],
    "backwardNav": ["back", "previous", "before"],
    "beginningNav": ["begin", "first"],
    "endingNav": ["final", "last"],
    "doneNav": ["exit", "done"],
    "otherNav": ["repeat", "th step", "st step", "nd step", "rd step"],
    "questions": ["How do I", "How to", "How many steps are there?"]}

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
        userRecipeURL = input("\nHello, I am your " + self.name + "! If you are ready, go ahead and type in a URL that points to a recipe you would like to work on: ")
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
    # Params: prompt (what we are asking of the user), validAns                #
    # (valid answers), buildAns (if true, then we need to build the closest    #
    # valid answer)                                                            #
    # Returns: userDecision (what the user wants to do next).                  #
    # Notes: Asks and waits until the user gives a valid input.                #
    ############################################################################
    def _processCommand(self, prompt, validAns, buildAns = False):
        userDecision = input(prompt)

        if buildAns: # Then you need to check for a valid answer against the set of known commands
            lowestEditDist = float("inf")
            bestCmd = None

            # If someone said "yes" or something like that, then we should repeat the current step
            if userDecision.lower() == "yes" or userDecision.lower() == "y":
                return "repeat"
            else: # But if they said no without saying what to do next
                while userDecision.lower() == "no" or userDecision.lower() == "n":
                    userDecision = self._processCommand("\nWhat should I do next then?: ", None, True)

            # Check for navigation commands first
            for navType in self.botCommandTypes["navTypes"]:
                for navCmd in self.botCommands[navType]:
                    if navCmd in userDecision.lower():
                        return userDecision.lower()

            # Now for the "how to" commands
            for howToCmd in self.botCommands["questions"]:
                loweredHowToCmd = howToCmd.lower() # Make comparisons more forgiving for the user
                if loweredHowToCmd == "how do i do that?":
                    if edit_distance(userDecision.lower(), "how do i do that?") < 2: # This gets a special case for itself
                        return "How do I do that?"
                else: # This may seem a bit odd, but hopefully the comments explain the logic well
                    splitDecision = userDecision.lower().split(" ") # The issue with general "how do I ...?" is that we don't know what is in the ...
                    howToCmdSplit = loweredHowToCmd.split(" ") # So we need to compare the edit distance of the first x words of each command
                    if len(splitDecision) >= len(howToCmdSplit): # Where x is the length of a valid bot command
                        # So "How do I cook the food?" would match "How do I" since the first 3 words match, but "How does that..." would not match "How do I"
                        if edit_distance(" ".join(splitDecision[:len(howToCmdSplit)]), loweredHowToCmd) < lowestEditDist and \
                        edit_distance(" ".join(splitDecision[:len(howToCmdSplit)]), loweredHowToCmd) < 2:
                            bestCmd = howToCmd + " " + " ".join(splitDecision[len(howToCmdSplit):]) # Construct "best command" with user given context
                            lowestEditDist = edit_distance(" ".join(splitDecision[:len(howToCmdSplit)]), loweredHowToCmd)

            if not bestCmd is None:
                return bestCmd # Return the best command found
            else: # If you got here, then we need to redo the above checks after getting a new command
                userDecision = self._processCommand("\nI'm afraid that I do not understand that command. Please try again, and if there were numerical prompts, enter just the number: ",
                None, True)

        else: # It is a straightforward check otherwise
            while userDecision.lower() not in validAns:
                userDecision = input("\nI'm afraid that I do not understand that command. Please try again, and if there were numerical prompts, enter just the number: ")

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
        givenCommand = int(self._processCommand("\nWould you like me to [1] move on to the first step or [2] repeat the list? Enter your choice here: ",
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
    # zero-indexed), printInst (tells the script whether to print the          #
    # instruction)                                                             #
    # Returns: None                                                            #
    # Notes: Helps the user navigate through instructions and handles anything #
    # anything that requires an external resource (Google, YouTube, etc.).     #
    ############################################################################
    def _instructionNavigation(self, currentStep, printInst = True):
        if len(self.recipeData["instructions"]) == currentStep : # If the current step goes past the last possible instruction number, then we are done
            print("\n------------------------------------------------------------------------")
            print("\nLooks like you're all done! Good work and enjoy your food! Thanks for using " + self.name + " and see you next time!\n")
            return True # Once the program sees true, everything should unwind quietly
        else:
            for key in self.instPredicates.keys():
                instOfInterest = self.instPredicates[key]
                if key == currentStep: # If this is the instruction we are dealing with
                    if printInst: # Check if we need to print the instruction (False if this was recursed on by an external resource command)
                        print("\n------------------------------------------------------------------------")
                        if currentStep == 0:
                            print("\nThe 1st step is: " + instOfInterest["sentence"])
                        elif currentStep == 1:
                            print("\nThe 2nd step is: " + instOfInterest["sentence"])
                        elif currentStep == 2:
                            print("\nThe 3rd step is: " + instOfInterest["sentence"])
                        else:
                            print("\nThe " + str(key + 1) + "th step is: " + instOfInterest["sentence"])

                    # Come up with 3 different prompts and randomly pick
                    nextPrompts = ["\nLet me know what you would like to do next. I can repeat the instruction too: ",
                    "\nReady for another command. Let me know if I should repeat what I just said: ",
                    "\nWould you like me to repeat that? Otherwise, I am ready for whatever you would like to do next: "]
                    givenCommand = self._processCommand(nextPrompts[random.randint(0, len(nextPrompts) - 1)], None, True) # Valid commands are built in the function

                    if not self._handleNavCmds(givenCommand, currentStep) and not self._handleQuestions(givenCommand, currentStep, instOfInterest["sentence"]): # If for whatever reason, something goes completely wrong
                        print("\nI'm sorry, something went really wrong. You should not have reached this branch. Sous-chef will cycle back to the previous valid state.")
                        self._instructionNavigation(currentStep, printInst = False)

    ############################################################################
    # Name: _handleNavCmds                                                     #
    # Params: userCmd (the command the user gave), instIdx (the step that the  #
    # user is currently on)                                                    #
    # Returns: None                                                            #
    # Notes: Handles all commands that deal with navigating between            #
    # instructions.                                                            #
    ############################################################################
    def _handleNavCmds(self, userCmd, instIdx):
        if "repeat" in userCmd.lower(): # Repeat the instruction
            self._instructionNavigation(instIdx)

        elif "th step" in userCmd.lower() or \
        "st step" in userCmd.lower() or \
        "nd step" in userCmd.lower() or \
        "rd step" in userCmd.lower(): # It's a "Take me to the nth step" command
            splitCmd = userCmd.split(" ")
            for token in splitCmd:
                if "th" in token or "st" in token or "nd" in token or "rd" in token:
                    numberNextTo = None # This is the part of the phrase where the number will be found
                    if "th" in token:
                        numberNextTo = "th"
                    elif "st" in token:
                        numberNextTo = "st"
                    elif "nd" in token:
                        numberNextTo = "nd"
                    elif "rd" in token:
                        numberNextTo = "rd"

                    # Now we jump to the appropriate step (including error checking)
                    stepNum = token.replace(numberNextTo, "")
                    if stepNum.isdigit() or stepNum.replace("-", "").isdigit(): # Check for a number and jump there (extra check for negatives)
                        if int(stepNum) - 1 <= 0: # Don't look for the 0th step
                            print("\nYou would be going to an unreachable step. Please try another command.")
                            self._instructionNavigation(instIdx, printInst = False)
                        elif int(stepNum) > len(self.recipeData["instructions"]): # You try to jump too far ahead
                            print("""\nThis recipe does not have quite that many steps. If you would like to move to the last possible instruction, try \"Take me to the last step\".
                            There are """ + str(len(self.recipeData["instructions"])) + " steps in total.")
                            self._instructionNavigation(instIdx, printInst = False)
                        else:
                            self._instructionNavigation(int(stepNum) - 1)
                    elif stepNum == "fir": # "...first step" command that uses the word "first"
                        self._instructionNavigation(0)
                    elif stepNum == "la": # "...last step" command that uses the word "last"
                        self._instructionNavigation(len(self.recipeData["instructions"]) - 1)

        elif any([navCmd in userCmd.lower() for navCmd in self.botCommands["beginningNav"]]): # First step command (that does not use the word "first" - see above)
            self._instructionNavigation(0)

        elif any([navCmd in userCmd.lower() for navCmd in self.botCommands["endingNav"]]): # Last step command (that does not use the word "last" - see above)
            self._instructionNavigation(len(self.recipeData["instructions"]) - 1)

        elif any([navCmd in userCmd.lower() for navCmd in self.botCommands["forwardNav"]]): # Next step command
            self._instructionNavigation(instIdx + 1)

        elif any([navCmd in userCmd.lower() for navCmd in self.botCommands["backwardNav"]]): # Previous step command
            if instIdx - 1 < 0: # Don't look for the 0th step
                print("\nYou would be going to an unreachable step. Please try another command.")
                self._instructionNavigation(instIdx, printInst = False)
            else:
                self._instructionNavigation(instIdx - 1)

        elif any([navCmd in userCmd.lower() for navCmd in self.botCommands["doneNav"]]): # If the user just says that they are done
            self._instructionNavigation(len(self.recipeData["instructions"])) # Goes to the ending branch instead of a hard exit

        else:
            return False # Not a navigation command

        return True # Probably not needed, but here for completeness

    ############################################################################
    # Name: _handleQuestions                                                   #
    # Params: userCmd (the command the user gave), instIdx (the step that the  #
    # user is currently on), instruction (current instruction)                 #
    # Returns: None                                                            #
    # Notes: Handles all commands that deal with the user asking for more      #
    # information.                                                             #
    ############################################################################
    def _handleQuestions(self, userCmd, instIdx, instruction):
        if "how do" in userCmd.lower() or "how to" in userCmd.lower(): # All the "how to" questions
            queryToUse = None # This is the query that gets used

            if "how do i do that" in userCmd.lower() or "how to do that" in userCmd.lower(): # Specific to the general "how to" question
                queryToUse = "How do I " + instruction + " when it comes to cooking"

            elif "how do i" in userCmd.lower() or \
            "how to" in userCmd.lower(): # Any vague "how to" command
                queryToUse = self._generateQuery(userCmd, instruction)

            try: # First try searching YouTube
                searchRes = json.loads(YoutubeSearch(queryToUse + " when it comes to cooking", max_results=1).to_json())["videos"][0] # Get the search result
                print("\nThere's a YouTube video that may be of some help. Check this out: " + \
                "https://www.youtube.com" + searchRes["url_suffix"])
                userResponse = self._processCommand("\nDoes this answer your question? (Y or Yes/N or No): ", ["yes", "no", "y", "n"])
                if userResponse.lower() == "n" or userResponse.lower() == "no": # If the YouTube search is not enough, try Google
                    searchRes = search(queryToUse + " when it comes to cooking")[0] # Get the first Google result
                    print("\nThere's a Google result that may be of some additional help. Check this out: " + searchRes)
            except: # If we cannot fetch anything from YouTube, try Google
                if not queryToUse is None: # Extra layer of checking
                    searchRes = search(queryToUse + " when it comes to cooking")[0] # Get the first Google result
                    print("\nThere's a Google result that may be of some help. Check this out: " + searchRes)
                else:
                    return False
            self._instructionNavigation(instIdx, printInst = False)

        elif "how many steps are there" in userCmd.lower():
            print("\nThere are " + str(len(self.instPredicates.keys())) + " steps.")
            self._instructionNavigation(instIdx, printInst = False)

        else: # Not a question that we can understand
            return False

        return True # Probably not needed, but here for completeness

    ############################################################################
    # Name: _generateQuery                                                     #
    # Params: currCmd (the command that triggered the query),                  #
    # currStep (the instruction the user is currently working on)              #
    # Returns: None                                                            #
    # Notes: Based on any ambigous phrasing in the user's question, we replace #
    # the ambiguous words with the parsed ingredients in the current step.     #
    ############################################################################
    def _generateQuery(self, currCmd, currStep):
        if "that" in currCmd: # We need to specify "how do I cook that?"
            for ing in self.ingPredicates:
                if self.ingPredicates[ing]["isa"] in currStep: # Look for the first ingredient you see in the query and just return that
                    return currCmd.replace("that", self.ingPredicates[ing]["isa"])
        elif "those" in currCmd: # Specify "how do I cook those?"
            newCmd = currCmd.replace("those", "") # First get rid of the vague word
            for ing in self.ingPredicates:
                if self.ingPredicates[ing]["isa"] in currStep: # Append each detected ingredient to the query
                    newCmd += ", " + self.ingPredicates[ing]["isa"]
            return newCmd
        else:
            return currCmd

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
