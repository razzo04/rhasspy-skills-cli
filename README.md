# Rhasspy skills cli
This application can be used to install, create and delete skills managed by [rhasspy skills](https://github.com/razzo04/rhasspy-skills). Can be installed using pip and depends on git to work properly.

```bash
pip install rhasspy-skills-cli
```
# Install new skill
To install a new skill is very simple, you just need to specify the name. 
```bash
rhskill install time_examples
```
The application will clone the repositories passed with the flag "--repositories" by default will use the [examples repository](https://github.com/razzo04/rhasspy-skills-examples.git) and then will search for the skill with the corresponding name. You can also install a local directory or tar archive which contains the manifest.json. 

# Create new skill
To easily create a new skill you can use the sub-command create. If you pass the flag "-i", which stand for "--interactive", it will ask a series of prompt for helping the creation of the manifest.json.
```bash
rhskill create -i
```
You can also specify which template to use, in this way will be generated a functional skill based on the selected template. For now, the template simple consists of overwriting the manifest.json of a working skill but in the future will be added new functionality. Once as be created you can test by using:
```bash
rhskill install path/to/skill
```