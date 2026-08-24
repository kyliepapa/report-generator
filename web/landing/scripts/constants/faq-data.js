/** FAQ content for the Help overlay accordion. */
const FAQ_DATA = [
    {
        q: 'What is a Project ID and where do I find it?',
        a: 'CompanyCam is full of projects, & project names change all the time, so the program needs a more reliable way to search through the CompanyCam database & find the exact project you\'re looking for. It does that using the Project ID, a string of numbers unique to each project. You can find it in the URL of the project page, it is the only string of numbers in the URL. Just copy it over! If you can\'t find it, be sure you\'re on the project page, not another page like a report.'
    },
    {
        q: 'My project has a unit label format that doesn\'t fit any of the options, which do I click?',
        a: 'If identifying the location of the installation requires two tags, like a unit & building, click either 123 A or A 123. If it only takes one tag to determine location, click 123. All of the buttons are set up to handle a certain set of unusual cases. Give it a try & let me know if it doesn\'t work so I can add that special case. More info on How-To Slide 2.'
    },
    {
        q: 'Things are all over the place & wrong in the report, what happened & what do I do?',
        a: 'Don\'t worry! The thing about automation is that when something goes wrong, it often offsets the whole program. Some things to check that may be throwing your report out of whack: First, check the tags on the offending photos. The most common cause of misplaced photos is incorrect or incomplete tagging. Simply adjust the tags as needed on CompanyCam & rerun the program. Second, check your inputs on the landing page, such as the spelling of your Bathroom Inputs & if you clicked the right format option. Remember to use the How-To Walkthrough as a resource, and if things still aren\'t working, let me know.'
    },
    {
        q: 'What are some random fun facts about programming?',
        a: 'The first ever computer programmer was a woman named Ada Lovelace, born in 1815. The first computer "bug" was a literal moth found inside a computer in 1947, and that is where the term comes from. There are over 700 coding languages, yet 60-70% of projects use just the top five most popular languages. The popular language JavaScript was formulated in only 10 days, & the popular language Python was not named after the snake, but after Monty Python.'
    },
    {
        q: 'What are some random specs of this program?',
        a: 'This program is written using four languages: Python (Flask), HTML, CSS, & JavaScript. It also relies on multiple fluctuating text files, which provide & store important data. Not counting those text files, this program contains over 7,000 lines of code spread across about seven files. The program\'s heaviest task is generating the pdf report, though the feature that took the longest to code was actually the original sorting algorithm that the whole program would end up being based upon.'
    },
    {
        q: 'Why did the above FAQs have nothing to do with how to use this program?',
        a: 'I coded in space for 6 FAQs expecting to only have a few to start, because the others will be filled in as I receive questions & figure out what is legitimately being frequently asked. As the developer, I am way too familiar with my own program to know exactly what little things might trip up a user. So these last three FAQs are just placeholders until I have enough data.'
    },
];
