# Python Web API Template
This template contains all the needed components to start the development of a Web API in Python
## Creating my repository
<pre>
Who?: Only Technical Product Leads
</pre>
Creating a new repository from this template is very easy, just follow this steps:
1. Navigate to your organization and click `Repositories`
1. Click the `New repository` button
1. In the `Repository template` option select ***python.az-api-LEANIX_ACRONYM-CONTEXT***
1. In the `Owner` select your GitHun Organization
1. Give a name to your repository following the ***Repository naming convention*** described in the ***Annex*** section at the end of this article
1. Give a proper description to your repository
1. Select `Python` as Language 
1. Click `Create repository`
1. Provide a name, description, and visibility for the new repository.
1. Include all branches from the template repository.
1. Click Create repository from template.

## Configuring my repository
Once you have created your repository, it's time to properly configuring it so you can make the most of the GitHub benefits
### Onboard your new repository into SonarQube
<pre>
Who?: Developers and Technical Product Leads
</pre>
1. Go to [SonarQube](https://senses.idb.iadb.org/projects)
1. Click `Create Project` and select `GitHub`
1. Chose your GitHub Organization
1. Select the repository to onboard

### Create your GitHub environments
<pre>
Who?: Only Technical Product Leads
</pre>
#### Continuous Integration environment
In IDB, the **CI is enforced** at GitHub enterprise level with policies. In order for your development to be in compliance with those policies, you must configure your CI environment
1. Navigate to your `Settings` repository
1. From the lef menu click `Environments`
1. Click `New environment`
1. Set the name to **continuous-integration** and click `Configure environment`
1. Scrolldown to the section **Environment variables**
1. Create `PROJECT_NAME` variable
    - Variable Name: PROJECT_NAME
    - Variable Value: {Product_Name} - {Repository_Name}
        - Note: For {Product_Name} use same name than the organization display name.
1. Create `PROJECT_KEY` variable
    - Variable Name: PROJECT_KEY
    - Variable Value: **SonarQube Project** Key created when repository was onboarded to [SonarQube](https://senses.idb.iadb.org/projects)
        - Note: You can get this KEY from your `Project Information` in [SonarQube](https://senses.idb.iadb.org/projects)

#### Azure login authentication methods
The reusable deployment workflows support two Azure login authentication methods for their deployment identities (App Registrations):

- **OIDC (federated credentials)** *(recommended)*: No client secret is required. GitHub exchanges a short-lived token with Azure, eliminating secret rotation concerns. Organizations created on or after **2026-03-08** natively support OIDC — the Developer Platform Team has already provisioned the necessary App Registrations, so no additional App Registration creation is needed by the Product Team.
- **Client secret** *(obsolete)*: Still functional but no longer recommended and **not supported by the Developer Platform Team**. Avoid using this method for new environments.

> **Default setup**: one shared App Registration per environment is provided automatically.
>
> **Recommendation for sensitive or COSO applications**: use one dedicated App Registration per repository per environment. To set this up, the Product Team must request a new deployment identity from the Developer Platform Team. The Developer Platform Team will supply the corresponding `CLIENT_ID` values, which the Tech Lead or TPO must then configure at the Environment level.

> **Allowed environment names**: `production`, `staging`, `test`, `qa`, `development`. If you require additional environments, contact the Developer Platform Team.

#### Non-production environments
These environments are less restricted than production and are used to deploy applications. Each non-production environment requires the following variables to be configured.
1. Navigate to your repository `Settings`
2. From the left menu click `Environments`
3. Click `New environment`
4. Set the name for your non-production environment using the full name (for example, ***development***) and click `Configure environment`
5. Scroll down to the section **Environment variables**
6. Create `SUBSCRIPTION_ID` variable
    - Variable Name: SUBSCRIPTION_ID
    - Variable Value: Azure subscription where your resource group belongs to.
7. Create `CLIENT_ID` variable
    - Variable Name: CLIENT_ID
    - Variable Value: Client ID of the App Registration (deployment identity) used for deployment. Provided by the Developer Platform Team.
8. Create `AZURE_RESOURCE_NAME` variable
    - Variable Name: AZURE_RESOURCE_NAME
    - Variable Value: Name of the resource where the code will be deployed.

> **Note**: When using OIDC authentication (default for organizations created on or after 2026-03-08), no `CLIENT_SECRET` is needed at the environment level.

#### Production environment
This environment is restrictive and designed for deployments to production. **It is important** to correctly configure branch restrictions and approvals to prevent unauthorized deployments to production.
1. Navigate to your repository `Settings`
2. From the left menu click `Environments`
3. Click `New environment`
4. Set the name to **production** and click `Configure environment`
5. Check the box `Required reviewers`
    - Configure the reviewers by searching for them in the `Add reviewers` search box.
    - For better maintenance, add groups instead of individuals.
    - Do not add developers to the group, as this would grant them permission to deploy.
6. Check the box `Prevent self-review`.
7. Scroll down to `Deployment branches and tags`.
    - Set the restriction from `No restriction` to `Selected branches and tags`
    - A button labeled `Add deployment branch or tag rule` will appear; click it to add the branches that will have permission to execute deployments.
    - Add this pattern to deploy semantic version release tags: `v[0-9]*.[0-9]*.[0-9]*`
8. Click on `Save protection rules`
9. Scroll down to the section **Environment variables**
10. Create `SUBSCRIPTION_ID` variable
    - Variable Name: SUBSCRIPTION_ID
    - Variable Value: Azure subscription where your resource group belongs to.
11. Create `CLIENT_ID` variable
    - Variable Name: CLIENT_ID
    - Variable Value: Client ID of the App Registration (deployment identity) used for deployment. Provided by the Developer Platform Team.
12. Create `AZURE_RESOURCE_NAME` variable
    - Variable Name: AZURE_RESOURCE_NAME
    - Variable Value: Name of the resource where the code will be deployed.

> **Note**: When using OIDC authentication (default for organizations created on or after 2026-03-08), no `CLIENT_SECRET` is needed at the environment level.


## Adjust the pre-defined GitHub Worflows
<pre>
Who?: Developers
</pre>
### .github/workflows folder
This is where your GitHub worflows go. This template contains the basics you need to build your `Continuous Integration Pipeline(CI)/Continuous Delivery Pipeline(CDel)` pipeline. 
1. Create a `feature` branch following the [***Branch naming convention***](#branching-naming-convention) described in the [***Annex***](#annex) section at the end of this article.
#### Continuous Integration and Continuous Delivery
These worflows are your ***CI/CDel***. The ***CI/CDel*** will be triggered every time a `push` is performed into your `feature` branch and the ***CDel*** will be triggered when a new `version tag` is generated in main.

(OPTIONAL)
1. Adjust the `continuous-integration.yml` and `continuous-delivery.yml` files with your JFROG_TOKEN (if needed) 
    - Note: Make sure that you have requested the creation of your ***JFrog repository*** in advance.
#### Continuous Deployment
Reusable workflows already have everything necessary for standard deployment and do not require additional inputs beyond those already written in this template. 

#### Auto tag worflow
This template comes with workflow (autotag-version.yml) which automates the creation of the `version tag` using [Release Please Action](https://github.com/marketplace/actions/release-please-action) by ***Google***. This action is based on the [Coventional Commits Specification](https://www.conventionalcommits.org/). Please read and learn it to perform quality versiong process.

## The README.md  file
This `readme` file that you are reading is part of your repository, so make sure to  modify it based on your needs to properly document your repository content.

## The pull_request_template.md
The markdown file in `.github/pull_request_template.md` it is a template for each pull request opened in the repository. It can be modified according to the team's preferences to include information or details about the PR that will be merged into main.


## Annex
### Repository naming convention
The IDB naming convention for repositories is as follow:</br>
**CLOUD_NAME-LEANIX_RESOURCE_PREFIX-LEANIX_ACRONYM-CONTEXT**</br>
#### Where:

- CLOUD_NAME:
    - az:  Azure
    - aws: Amazon Web Services
    - sp:  Sharepoint
    - sf:  Salesforce
    - pt:  Pantheon

- LEANIX_RESOURCE_PREFIX:
    - Azure: [Azure LeanIX invetory](https://iadb.leanix.net/IADBProduction/inventory/3e0e89e1-41bf-4c36-90b0-727ca6f9077b)
    - AWS: [AWS LeanIX invetory](https://iadb.leanix.net/IADBProduction/inventory/9ba241b2-7256-49fc-87f2-4c5f5bb7331a)
    - Addtional prefixes:
        - iac: Infraestructure as a Code (Terraform)
        - docs: Documentation
        - wf: GitHub Workflows

- LEANIX_ACRONYM: Acronym of your application registered in [LeanIX](https://iadb.leanix.net/IADBProduction)
    - Example: cms (Cash Management System)

- CONTEXT: Some extra contexts to help understand the purpose of the repository content
#### Example of repository name: 
***az-fn-cms-statements-preprocessor<br>***
This respository contains a component hosted in "Azure `(CLOUD_NAME)`" and runs in an "Azure Function `(LEANIX_RESOURCE_PREFIX)`" <br>
The component is part of "CMS `(LEANIX_ACRONYM)`" and its name is "Statements Preprocessor `(CONTEXT)`"

### Branching naming convention
The IDB naming convention for repositories is based on the allowed **Branching models" to work with:</br>

#### Trunk-base development model (encourage)
Branches:
- main: This the trunk of your work flow.
- feature/{JIRA_PROJECT_KEY}: This where you implement the new funcionalities that will be incorporated to the trunk in some point of the future.
##### Where:
- {JIRA_PROJECT_KEY: The KEY of your JIRA project.

#### GitLab Flow development model
Branches:
- main: This the trunk of your work flow.
- feature/{JIRA_PROJECT_KEY}: This where you implement the new funcionalities that will be incorporated to the trunk in some point of the future.
- production, staging, test, qa, develop: Used as snapshot and triggers for production when pushed changes.
##### Where:
- {JIRA_PROJECT_KEY: The KEY of your JIRA project.