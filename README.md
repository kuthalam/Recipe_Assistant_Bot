# Recipe_Assistant_Bot
Project 3 repository for CS 337: NLP

# Running the code
Please follow the two installation steps below:
* First run `conda env create --name <myEnvName> -f environment.yml`
* Then an additional command is needed to get the dependency parser working: `python3 -m spacy download en_core_web_sm`
    * For some reason, `pip freeze` was not enough to get the `environment.yml` file to take care of this.

To run the code, you just need to enter `python recipeBot.py`
* It will ask you to paste in a recipe from allRecipes.com
* An example of a valid recipe that the code expects: https://www.allrecipes.com/recipe/24345/shredded-potato-quiche/
* If the recipe instructions come as a video without written instructions and/or ingredients, our parser would fail.

# General Overview of the Kind of Questions Our Bot Can Handle
* Navigation commands:
  * If you want the bot to repeat what it just said, then either tell it "yes" or something with the word "repeat".
  * Moving on to the next step requires typing any statement with "forward", "next", or "after".
  * Going to the previous step requires typing any statement with "back", "previous", or "before".
  * The bot can also jump to any step, so long as you give a statement with the appropriate number in it.
    * Example 1: Take me to the 6th step
    * Example 2: Take me to the 3rd step
    * On that note, you can also say "take me to the first step" and "take me to the last step".
      * However, the request needs to have one of the following words to work as expected: "begin", "first", "final", "last"
  * At any point, you can say "Ok, I'm done cooking" and the bot will behave as though you finished the recipe.
    * By this, we mean you will get a message showing that you are done and the program has exited.

* "How to" commands:
  * You can ask, at any time, questions that begin with "how do I" or "how to"
  * The query will then be sent to a YouTube API and a YouTube video will be returned.
    * The bot will ask if this answers your question. If not, then a Google result will be returned.
    * If the API could not return a video that it found, a Google result will be returned instead.

* If there are numbers given with the bot's prompt, please always enter those.
* If a command that the bot does not understand, it will let you know and you can try again.
* Once you go to the last step, you can exit by just trying to go to the next step.
