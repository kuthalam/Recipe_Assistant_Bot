# Recipe_Assistant_Bot
Project 3 repository for CS 337: NLP

# Running the code
Once you run `pip install -r requirements.txt`, everything should be good to go.
* If it is not for some reason, please follow these steps:
  * Start with the `requirements.txt` file from project 2 that the team was emailed
  * Then run `pip install youtube-search`
  * Then `pip install googlesearch-python`
  * Finally, run `python3 -m spacy download en_core_web_sm`
  * Everything should work as expected from here

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
    * Example 2: Take me to the third step
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
