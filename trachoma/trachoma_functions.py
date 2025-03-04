import numpy as np
from datetime import date
import matplotlib.pyplot as plt
import pandas as pd
import copy
import math
from numpy import ndarray
from numpy.typing import NDArray
from dataclasses import dataclass
from typing import Callable, List, Optional
from pathlib import Path

DEFAULT_DATA_PATH = Path(__file__).parent / "data" / "coverage"

"""
This file contains helper functions for running simulations.
A single simulation can be run using run_single_simulation.
Otherwise simulations are run using the sim_Ind_MDA_XXXX functions.
"""

@dataclass
class Result:
    time: float
    IndI: ndarray
    IndD: ndarray
    Age:ndarray
    NoInf: ndarray
    nMDA:Optional[ndarray] = None
    nMDADoses: Optional[ndarray] = None
    nVacc:Optional[ndarray] = None
    nVaccDoses: Optional[ndarray] = None
    nSurvey: Optional[int] = None
    surveyPass: Optional[int] = None
    elimination: Optional[int] = None
    propMDA: Optional[ndarray] = None    
    propVacc: Optional[ndarray] = None    
    
    
def outputResult(vals, i, nDoses, coverage, nMDA, nSurvey, surveyPass, true_elimination, nVacc, nVaccDoses, propVacc):
    return (Result(time = i,
                          IndI = vals['IndI'], 
                          IndD = vals['IndD'], 
                          Age = vals['Age'], 
                          NoInf = vals['No_Inf'],
                          nMDADoses = nDoses, 
                          nSurvey = nSurvey,
                          surveyPass = surveyPass,
                          elimination = true_elimination,
                          propMDA = coverage,
                          nMDA = nMDA,
                          nVacc = nVacc, 
                          nVaccDoses = nVaccDoses,
                          propVacc = propVacc))


def _validate_data_path(data_path):
    """
    Set data path to default is None, otherwise check that path
    actually exists.
    """
    if data_path:
        try:
            data_path = Path(data_path)
        except TypeError as e:
            sys.stderr(f"ERROR: {data_path} is not a valid data path")
            raise e
        if not data_path.exists():
            raise FileNotFoundError(
                f"ERROR: {data_path} does not exists"
            )
        return data_path

    return DEFAULT_DATA_PATH


def readPlatformData(coverageFileName, Platform, data_path=None):
    PlatCov = pd.read_csv(
        _validate_data_path(data_path) / coverageFileName
    )
    PlatformRows = np.where(PlatCov.Platform == Platform)[0]
    if(len(PlatformRows) >0):
        PlatCov = PlatCov.iloc[PlatformRows, :]
         # we want to find which is the first year specified in the coverage data, along with which
         # column of the data set this corresponds to
        fy = 10000
        fy_index = 7
        for i in range(len(PlatCov.columns)):
            if type(PlatCov.columns[i]) == int:
                fy = min(fy, PlatCov.columns[i])
                fy_index = min(fy_index, i)
    
        count = 0
        minAgeIndex = np.where(PlatCov.columns == "min age")[0][0]
        maxAgeIndex = np.where(PlatCov.columns == "max age")[0][0]
        for i in range(fy_index, len(PlatCov.columns)):
            dd = PlatCov.iloc[:, i]
            PlatformS = np.where(dd>0)[0]
            if len(PlatformS)>0:
                for k in range(len(PlatformS)):
                    j = PlatformS[k]
                    if count == 0:
                        PlatformData = [[float(PlatCov.columns[i]), PlatCov.iloc[j, minAgeIndex], PlatCov.iloc[j, maxAgeIndex], PlatCov.iloc[j, i], j,  PlatCov.shape[0]]]
                        count += 1
                    else:
                        PlatformData.append([float(PlatCov.columns[i]), PlatCov.iloc[j, minAgeIndex], PlatCov.iloc[j, maxAgeIndex], PlatCov.iloc[j, i], j,  PlatCov.shape[0]])
                        count +=1
        if count == 1:
            PlatformData.append([3026.0, 2, 5, 0.6, 0, 2])
        if count == 0:
            PlatformData = [[3026.0, 2, 5, 0.6, 0, 2]]
            PlatformData.append([3026.0, 2, 5, 0.6, 0, 2])
    else:
        PlatformData = [[3026.0, 2, 5, 0.6, 0, 2],
                   [3026.0, 2, 5, 0.6, 0, 2]]
    return PlatformData
               

def getInterventionDates(InterventionData):
    for i in range(len(InterventionData)):
        d = InterventionData[i][0]
        y = int(d)
        m = round(12*(d - int(d))) + 1
        day = 1
        if i == 0:
            Intervention_dates = [date(y, m, day)]
        else:
            Intervention_dates.append(date(y, m, day))
    return Intervention_dates
 


def getOutputTimes(outputTimes):
    for i in range(len(outputTimes)):
        d = outputTimes[i]
        y = int(d)
        m = 6
        day = 1
        if i == 0:
            modOutputTimes = [date(y, m, day)]
        else:
            modOutputTimes.append(date(y, m, day))
    return modOutputTimes

def vaccinate_population(vals = None, params = None):
    '''
    Vaccinate population according to coverage provided in `params`

    Parameters
    ----------
    params : dict 
        Parameter dictionary with all parameters not associated with MDA

    vals : dict
        Contains current state of simulation

    Returns
    -------
    dict
        vals

    '''
    # randomly vaccinated population according to coverage
    index_vaccinated = np.random.rand(params['N']) < params['vacc_coverage']
    vals['vaccinated'][index_vaccinated] = True
    vals['time_since_vaccinated'][index_vaccinated] = 0

    return vals

def stepF_fixed(vals, params, demog, bet, distToUse = "Poisson"):

    '''
    Step function i.e. transitions in each time non-MDA timestep.
    '''

    #Step 0: do importation of infection 
    import_indivs = np.where(np.random.uniform(size = params['N']) < params['importation_rate'])[0]
    if len(import_indivs) > 0:
        vals = Import_individual(vals, import_indivs, params, demog, distToUse)

    # Step 1: Identify individuals available for infection.
    # Susceptible individuals available for infection.
    Ss = np.where(vals['IndI'] == 0)[0]
    # we only care about bacterial load when we use it to calculate infection probabilities.
    # This is done in the getlambdaStep function, so update the bacterial loads before calling this function
    vals['bact_load'] = bacterialLoad(params = params, vals = vals)
    # Step 2: Calculate infection pressure from previous time step and choose infected individuals
    # Susceptible individuals acquiring new infections. This gives a lambda
    # for each individual dependent on age and disease status.
    lambda_step = 1 - np.exp(- getlambdaStep(params=params, Age=vals['Age'], bact_load=vals['bact_load'],
    IndD=vals['IndD'], vaccinated=vals['vaccinated'],time_since_vaccinated=vals['time_since_vaccinated'],
    bet=bet, demog=demog))
    # New infections
    newInf = Ss[np.random.uniform(size=len(Ss)) < lambda_step[Ss]]

    # Step 3: Identify transitions
    newDis = np.where(vals['T_latent'] == 1)[0]  # Designated latent period for that individual is about to expire
    newClearInf = np.where(vals['T_ID'] == 1)[0]  # Designated infectious period for that individual is about to expire
    newClearDis = np.where(vals['T_D'] == 1)[0]  # Designated diseased period for that individual is about to expire
    newInfectious = np.where(np.logical_and(vals['IndI']==1,vals['T_latent']==1))[0] # Only individuals who have avoided MDA become infectious at end of latent

    # Step 4: reduce counters
    # Those in latent period should count down with each timestep.
    vals['T_latent'][vals['T_latent'] > 0] -= 1
    # Those infected should count down with each timestep
    vals['T_ID'][vals['T_ID'] > 0] -= 1
    # Those diseased should count down with each timestep
    vals['T_D'][vals['T_D'] > 0] -= 1

    # Step 5: implement transitions
    # Transition: become diseased (and infected)
    vals['IndD'][newDis] = 1  # if they've become diseased they become D=1
    vals['T_ID'][newDis] = ID_period_function(newDis, params=params, vals = vals)
    #vals['T_D'][newDis] = 0  # SS Added to prevent transition of doom.
    # Transition: Clear infection
    vals['IndI'][newClearInf] = 0  # clear infection they become I=0
    # When individual clears infection, their diseased only is set
    vals['T_D'][newClearInf] = D_period_function(Ind_D_period_base=vals['Ind_D_period_base'][newClearInf],
    No_Inf=vals['No_Inf'][newClearInf], params=params, Age = vals['Age'][newClearInf])
    # Transition: Clear disease
    vals['IndD'][newClearDis] = 0  # clear disease they become D=0

    # Step 6: implement infections
    # Transition: become infected
    vals['IndI'][newInf] = 1  # if they've become infected, become I=1
    # When individual becomes infected, set their latent period;
    # this is how long they remain in category I (infected but not diseased)
    vals['T_latent'][newInf] = vals['Ind_latent'][newInf]
    # New infected can be D and have nonzero T_D/T_ID
    vals['T_D'][newInf] = 0
    vals['T_ID'][newInf] = 0

    # Tracking infection history
    vals['No_Inf'][newInf] += 1

    # update vaccination history
    vals['time_since_vaccinated'][np.where(vals['vaccinated'])] += 1

    # Update age, all age by 1w at each timestep, and resetting all "reset indivs" age to zero
    # Reset_indivs - Identify individuals who die in this timestep, either reach max age or random death rate
    vals['Age'] += 1
    reset_indivs = Reset(Age=vals['Age'], demog=demog, params=params)

    # Resetting new parameters for all new individuals created
    if(len(reset_indivs) > 0):
        vals = Reset_vals(vals, reset_indivs, params, distToUse)
    
    #me = 2
    #print(vals['Age'][me],vals['No_Inf'][me],vals['bact_load'][me],':',vals['IndI'][me],vals['IndD'][me],vals['T_latent'][me],vals['T_ID'][me],vals['T_D'][me])

    return vals


def get_Intervention_times(Intervention_dates, Start_date, burnin):
    Intervention_times = []
    for i in range(0, len(Intervention_dates)):
        Intervention_times.append(burnin + int((Intervention_dates[i] - Start_date).days/7))
    return np.array(Intervention_times)



def getlambdaStep(params, Age, bact_load, IndD, bet, demog,
    vaccinated,time_since_vaccinated):

    y_children = np.where(np.logical_and(Age >= 0, Age < 9 * 52))[0]  # Young children
    o_children = np.where(np.logical_and(Age >= 9 * 52, Age < 15 * 52))[0]  # Older children
    adults = np.where(Age >= 15 * 52)[0]  # Adults

    totalLoad = np.array([np.sum(bact_load[y_children]) / len(y_children),
    np.sum(bact_load[o_children]) / len(o_children), np.sum(bact_load[adults]) / len(adults)])
    prevLambda = bet * (params['v_1'] * totalLoad + params['v_2'] * (totalLoad ** (params['phi'] + 1)))

    a = len(y_children)/params['N']
    b = len(o_children)/params['N']
    c = len(adults)/params['N']
    epsm = 1 - params['epsilon']
    eps =  params['epsilon']
    # this was previously incorrectly specified in the python code, due to social mixing being wrong
    # and not accounting for all mixing done by age groups.
    # update with correct formulation which is described in equation 3 of the supplementary 
    # material of this paper https://journals.plos.org/plosntds/article?id=10.1371/journal.pntd.0000462
    A = [
        eps * prevLambda[0] + prevLambda[0]*a * epsm + prevLambda[1]*epsm*b + prevLambda[2]*epsm*c,
        prevLambda[0]*a*epsm + prevLambda[1]*b * epsm + eps * prevLambda[1] + prevLambda[2]*epsm*c,
        prevLambda[0]*a*epsm + prevLambda[1]*epsm*b + prevLambda[2]*c * epsm + eps * prevLambda[2],
    ]
    returned = np.ones(params['N'])
    returned[y_children] = A[0]
    returned[o_children] = A[1]
    returned[adults] = A[2]

    # add reduction in lambda according to who has been vaccinated
    prob_reduction = params["vacc_prob_block_transmission"]

    # add impact of waning using a linear slope. After waning period assumed vaccine has zero impact.
    prob_reduction = prob_reduction * (- time_since_vaccinated / params["vacc_waning_length"] + 1)
    prob_reduction = np.maximum(prob_reduction,0)

    returned[vaccinated] = (1 - prob_reduction[vaccinated]) * returned[vaccinated]

    # the factor of (0.5 + 0.5 * (1 - IndD)) reduces the infections pressure on people who are already diseased by 50%.
    return returned  * (0.5 + 0.5 * (1 - IndD))

def Reset(Age, demog, params):

    '''
    Function to identify individuals who either die due
    to background mortality, or who reach max age.
    '''

    return np.where(np.logical_or(np.random.uniform(size=params['N']) < 1 - np.exp(- demog['tau']), Age > demog['max_age']))[0]

def doMDAAgeRange(vals, params, ageStart, ageEnd):
    '''
    Decide who is cured during MDA based on treatment probabilities
    and probability of clearance given treated.
    '''
    Age = vals['Age'] 
    cured_babies = []
    cured_older = []
    treated_babies = []
    treated_older = []
    if ageStart*52 <= 26:
        babies = np.where(Age <= 26)[0]
        treated_babies = babies[np.where(np.random.uniform(size=len(babies)) < vals['treatProbability'][babies])[0]]
        cured_babies = treated_babies[np.random.uniform(size=len(treated_babies)) < (params['MDA_Eff'] * 0.5)]

        older = np.where(np.logical_and(Age > 26, Age <= ageEnd *52))[0]
        treated_older = older[np.where(np.random.uniform(size=len(older)) < vals['treatProbability'][older])[0]]
        cured_older = treated_older[np.random.uniform(size=len(treated_older)) < (params['MDA_Eff'])]
    else:
        older = np.where(np.logical_and(Age > ageStart * 52, Age <= ageEnd *52))[0]
        treated_older = older[np.where(np.random.uniform(size=len(older)) < vals['treatProbability'][older])[0]]
        cured_older = treated_older[np.random.uniform(size=len(treated_older)) < (params['MDA_Eff'])]
    return np.append(cured_babies, cured_older), np.append(treated_babies, treated_older)

def MDA_timestep_Age_range(vals, params, ageStart, ageEnd, t, label, demog):

    '''
    This is time step in which MDA occurs
    '''
    mda_t = t + label * 0.0001
    # Id who is treated and cured
    cured_people, treated_people = doMDAAgeRange(vals = vals, params=params, ageStart = ageStart, ageEnd = ageEnd)

    # Set treated/cured indivs infection status and bacterial load to 0
    vals['IndI'][cured_people.astype(int)] = 0       # clear infection they become I=0
    vals['bact_load'][cured_people.astype(int)] = 0  # stop being infectious
    vals['T_ID'][cured_people.astype(int)] = 0 # reset time in ID compartment
    vals['T_latent'][cured_people.astype(int)] = 0 # reset time in latent compartment

    treatedAges, _ = np.histogram(
                            vals["Age"][treated_people.astype(int)]/52, 
                            bins=np.arange(int(demog['max_age']/52) + 1))
    vals["n_treatments"][
            str(mda_t) + ", MDA (campaign " + str(label) + ")"
        ] = treatedAges
        
    n_people_by_age, _ = np.histogram(
            vals["Age"]/52,
            bins=np.arange(0, int(demog['max_age']/52)+ 1),
        )
    vals["n_treatments_population"][
            str(mda_t) + ", MDA (campaign " + str(label) + ")"
        ] = n_people_by_age
    
    return vals, len(treated_people)

def vacc_timestep_Age_range(params, vals, vacc_round, VaccData, t, demog):

    '''
    This is time step in which MDA occurs
    '''

    # Do vaccination for this vaccine round
    vals = doVaccAgeRange(params, vals, vacc_round, VaccData, t, demog)
    
   
    return vals


def doVaccAgeRange(params, vals, vacc_round, VaccData, t, demog):

    '''
    Decide who is vaccinated based coverage and age range    
    '''
    label = VaccData[vacc_round][4]
    vacc_t = t + label * 0.0001
    Age = vals['Age']
    ageStart = VaccData[vacc_round][1]
    ageEnd = VaccData[vacc_round][2]
    ageRange = np.logical_and(Age >= ageStart * 52, Age < ageEnd *52)
    index_vaccinated = np.random.rand(params['N']) < VaccData[vacc_round][3]
    vaccInAgeRange = np.logical_and(ageRange, index_vaccinated)
    vals['vaccinated'][vaccInAgeRange] = True
    vals['time_since_vaccinated'][vaccInAgeRange] = 0
    vals['nDosesVacc'][VaccData[vacc_round][-2]] += np.count_nonzero(vaccInAgeRange)
    vals['numVacc'][VaccData[vacc_round][-2]] += 1
    vals['coverageVacc'][VaccData[vacc_round][-2]] += np.count_nonzero(vaccInAgeRange)/np.count_nonzero(ageRange)

    vaccAges, _ = np.histogram(
                            vals["Age"][vaccInAgeRange]/52, 
                            bins=np.arange(int(demog['max_age']/52) + 1))
    vals["n_vaccinated"][
            str(vacc_t) + ", Vaccination (campaign " + str(label) + ")"
        ] = vaccAges
        
    n_people_by_age, _ = np.histogram(
            vals["Age"]/52,
            bins=np.arange(0, int(demog['max_age']/52)+ 1),
        )
    vals["n_vaccinated_population"][
            str(vacc_t) + ", Vaccination (campaign " + str(label) + ")"
        ] = n_people_by_age
    
    return vals


def ID_period_function(newDis, params, vals):

    '''
    Function to give duration of active infection.
    Add reduction in duration if additionally been vaccinated

    Parameters
    ----------
    newInfectious : np.array 
        boolean array denoting which individuals are newly infected
    params : dict
    vals : dict

    Returns
    -------
    np.array
        array of duration of infections subsetted by newInfectious
    '''
    Ind_ID_period_base  =vals['Ind_ID_period_base'][newDis]
    No_Inf = vals['No_Inf'][newDis]
    id_periods = 1/((1/Ind_ID_period_base - 1/params['min_ID']) * np.exp(-params['inf_red'] * (No_Inf - 1)) + 1/params['min_ID'])

    # If vaccinated reduce bacterial load by a fixed proportion
    prob_reduction = params["vacc_reduce_duration"]
    vaccinated = vals['vaccinated'][newDis]

    id_periods[vaccinated] = (1 - prob_reduction) * id_periods[vaccinated]

    # round to an integer
    id_periods = np.round(id_periods)

    return id_periods

def D_period_function(Ind_D_period_base, No_Inf, params, Age):

    '''
    Function to give duration of disease only period.
    '''
    ag = 0.00179
    aq = 0.0368
    T_D = np.round(1/((1/Ind_D_period_base - 1/params['min_D']) * np.exp(- params['dis_red'] * (No_Inf - 1)) + 1/params['min_D']))
    return T_D

def bacterialLoad(params,vals):

    '''
    Function to scale bacterial load according to infection history.
    Add reduction in bacterial load if additionally been vaccinated

    Parameters
    ----------
    newInfectious : np.array 
        boolean array denoting which individuals are newly infected
    params : dict
    vals : dict

    Returns
    -------
    np.array
        array of bacterial loads subsetted by newInfectious
    '''
    No_Inf = vals['No_Inf']
    b1 = 1
    ep2 = 0.114
    # we can calculate the bacterial load for everyone and then just see which
    # people have active infection and then multiply by an indicator of this.
    # the following line finds the people who have an active infection
    peopleWithNonZeroBactLoad = vals['T_ID'] > 0 
    bacterial_loads = b1 * np.exp(- (No_Inf-1) * ep2) * (peopleWithNonZeroBactLoad)
    
    # If vaccinated reduce bacterial load by a fixed proportion
    prob_reduction = params["vacc_reduce_bacterial_load"]
    vaccinated = vals['vaccinated']

    bacterial_loads[vaccinated] = (1 - prob_reduction) * bacterial_loads[vaccinated]

    return bacterial_loads



def drawTreatmentProbabilities(n, cov, snc):

    """
    Draw the treatment probabilities for the value of coverage and snc given.
    This uses the scheme explained in section 1.5.3 of the suppplement to this paper
    https://www.sciencedirect.com/science/article/pii/S1755436516300810?via%3Dihub#sec0110
    """

    if(cov == 0):
        return np.zeros(n)
    elif(cov == 1):
        return np.ones(n)
    elif(snc > 0):
        alpha = cov * (1-snc)/snc
        beta = (1-cov)*(1-snc)/snc
        return np.random.beta(alpha, beta, n)
    return np.ones(n) * cov 


def editTreatProbability(vals, cov, snc):

    """
    Choose new values for treatment probability (e.g. for when coverage or snc change)

    The rank of each individuals probability of treatement is retained
    I.e. if previously you were the most likely person to get treated, you still will be after this
    """

    if snc > 0:
        # Draw probabilities from the beta distribution
        treatProbabilities = drawTreatmentProbabilities(len(vals['IndI']), cov, snc)
        # Sort these values so that they are in ascending order so they can later be matched with people
        treatProbabilities.sort()

        # Store the current value of the treatProbability 
        oldTreatProbabilities = vals['treatProbability']

        # Sort the indices array based on the values in oldTreatProbabilities
        indices = np.argsort(oldTreatProbabilities)
        # Assign the newly drawn treatment probabilities to the appropriate individuals
        for rank, person_index in enumerate(indices):
            vals['treatProbability'][person_index] = treatProbabilities[rank]
    else:
        vals['treatProbability'] = np.ones(len(vals['IndI'])) * cov


def Set_inits(params, demog, sim_params, MDAData, numpy_state, distToUse = "Poisson"):

    '''
    Set initial values.
    '''

    np.random.set_state(numpy_state)
    MDA_coverage = 0
    treatProbability = np.full(shape=params['N'], fill_value=np.nan, dtype=float)
    systematic_non_compliance = params['rho']
    if distToUse == "Poisson":
        Ind_ID_period_base=np.random.poisson(lam=params['av_ID_duration'], size=params['N'])

            # Individual's baseline diseased period (first infection)
        Ind_D_period_base=np.random.poisson(lam=params['av_D_duration'], size=params['N'])
    else:
        Ind_ID_period_base= np.round(np.random.exponential(scale=params['av_ID_duration'], size=params['N']))

            # Individual's baseline diseased period (first infection)
        Ind_D_period_base= np.round(np.random.exponential(scale=params['av_D_duration'], size=params['N']))
        Ind_ID_period_base[Ind_ID_period_base == 0] = 1
        Ind_D_period_base[Ind_D_period_base == 0] = 1

    if (len(MDAData) > 0):
        MDA_coverage = MDAData[0][3]
        treatProbability = drawTreatmentProbabilities(params['N'], MDA_coverage, systematic_non_compliance)
    vals = dict(

        # Individual's infected status
        IndI=np.zeros(params['N']),

        # Individual's disease status
        IndD=np.zeros(params['N']),

        # Individual's total number of infections, should increase by 1 each time they become newly infected
        No_Inf=np.zeros(params['N']),

        # Duration of latent period (I), i.e. infected but not yet clinically diseased
        T_latent=np.zeros(params['N']),

        # Duration of current ID period, set when becomes infected and counts down with each time step
        T_ID=np.zeros(params['N']),

        # Duration individual spends diseased after clearing infection
        T_D=np.zeros(params['N']),

        # Individual's latent period (fixed for now)
        Ind_latent=params['av_I_duration'] * np.ones(params['N']),

        # Individual's baseline ID period (first infection)
        Ind_ID_period_base=Ind_ID_period_base,

        # Individual's baseline diseased period (first infection)
        Ind_D_period_base=Ind_D_period_base,

        # Baseline bacterial load set to zero
        bact_load=np.zeros(params['N']),

        # Age distribution
        Age=init_ages(params=params, demog=demog, numpy_state=numpy_state),

        # Number of MDA rounds
        N_MDA=sim_params['N_MDA'],

        # Prevalence
        True_Prev_Disease_children_1_9=[],
        
        vaccinated = np.full(params['N'], fill_value=False, dtype=bool),
        
        time_since_vaccinated = np.zeros(params['N']) ,
        
        treatProbability = treatProbability,

        MDA_coverage = MDA_coverage,

        systematic_non_compliance = systematic_non_compliance,

        ids = np.array(np.arange(params['N'])),
        n_treatments = {},
        n_treatments_population = {},
        n_surveys = {},
        n_surveys_population = {},
    )

    return vals

def Reset_vals(vals, reset_indivs, params, distToUse = "Poisson"):

    '''
    Set initial values.
    '''
    numResetIndivs = len(reset_indivs)
    maxID = max(vals['ids'])
    vals['Age'][reset_indivs] = 0
    vals['IndI'][reset_indivs] = 0
    vals['IndD'][reset_indivs] = 0
    vals['No_Inf'][reset_indivs] = 0
    vals['T_latent'][reset_indivs] = 0
    vals['T_ID'][reset_indivs] = 0
    vals['T_D'][reset_indivs] = 0
    vals['vaccinated'][reset_indivs] = False
    vals['time_since_vaccinated'][reset_indivs] = 0
    if distToUse == "Poisson":
        vals['Ind_ID_period_base'][reset_indivs] = np.random.poisson(lam=params['av_ID_duration'], size=numResetIndivs)
        vals['Ind_D_period_base'][reset_indivs] = np.random.poisson(lam=params['av_D_duration'], size=numResetIndivs)
    else:
        ID_periods = np.round(np.random.exponential(scale=params['av_ID_duration'], size=numResetIndivs))
        ID_periods[ID_periods == 0] = 1
        vals['Ind_ID_period_base'][reset_indivs] = ID_periods
        D_periods = np.round(np.random.exponential(scale=params['av_D_duration'], size=numResetIndivs))
        D_periods[D_periods == 0] = 1
        vals['Ind_D_period_base'][reset_indivs] = D_periods
    
    vals['bact_load'][reset_indivs] = 0
    vals['treatProbability'][reset_indivs] = drawTreatmentProbabilities(numResetIndivs, vals['MDA_coverage'], vals['systematic_non_compliance']),
    new_ids = np.arange(maxID + 1, maxID + numResetIndivs + 1)
    vals['ids'][reset_indivs] = new_ids
    return vals

def Import_individual(vals, import_indivs, params, demog, distToUse = "Poisson"):
    '''
    When someone is imported, we assume that they are infected and diseased and some random proportion
    of time through their infection period. We will assume that they are at the average number of infecteds
    for the whole population in order to draw these times too.
    '''
    ages = np.arange(1, 1 + demog['max_age'])

    # ensure the population is in equilibrium
    propAges = np.empty(len(ages))
    propAges[:-1] = np.exp(-ages[:-1] / demog['mean_age']) - np.exp(-ages[1:] / demog['mean_age'])
    propAges[-1] = 1 - np.sum(propAges[:-1])
    numImportIndivs = len(import_indivs)
    vals['Age'][import_indivs] = np.random.choice(a=ages, size=numImportIndivs, replace=True, p=propAges)

    vals['IndI'][import_indivs] = 1
    vals['IndD'][import_indivs] = 1
    vals['No_Inf'][import_indivs] = max(1, round(np.mean(vals['No_Inf'])))
    if distToUse == "Poisson":
        vals['Ind_ID_period_base'][import_indivs] = np.random.poisson(lam=params['av_ID_duration'], size=numImportIndivs)
        vals['Ind_D_period_base'][import_indivs] = np.random.poisson(lam=params['av_D_duration'], size=numImportIndivs)
    else:
        ID_periods = np.round(np.random.exponential(scale=params['av_ID_duration'], size=numImportIndivs))
        ID_periods[ID_periods == 0] = 1
        vals['Ind_ID_period_base'][import_indivs] = ID_periods
        D_periods = np.round(np.random.exponential(scale=params['av_D_duration'], size=numImportIndivs))
        D_periods[D_periods == 0] = 1
        vals['Ind_D_period_base'][import_indivs] = D_periods
    vals['T_latent'][import_indivs] = 0
    vals['T_ID'][import_indivs] = ID_period_function(import_indivs, params, vals) * np.random.uniform()
    vals['T_D'][import_indivs] = 0
    vals['vaccinated'][import_indivs] = False
    vals['time_since_vaccinated'][import_indivs] = 0

    vals['bact_load'] = bacterialLoad(params, vals)
    vals['treatProbability'][import_indivs] = drawTreatmentProbabilities(numImportIndivs, vals['MDA_coverage'], vals['systematic_non_compliance'])
    return vals


def Seed_infection(params, vals):

    '''
    Seed infection.
    '''

    # set 1% to infected, can change if want to seed more, may need to if want to simulate
    # low transmission settings to stop stochastic fade-out during burn-in
    vals['IndI'][:int(np.round(params['N'] * 0.01))] = 1

    Init_infected = np.where(vals['IndI'] == 1)[0]

    # set latent period for those infected at start of simulation
    vals['T_latent'][Init_infected] = vals['Ind_latent'][Init_infected]

    # set number of infections to 1 for those infected at start of simulation
    vals['No_Inf'][Init_infected] = 1

    return vals

def Check_for_IDs(vals):
    '''
    Check if "id" key is in `vals`. If they are
    not then initialize for population
    
    Parameters
    ----------
    
    params : dict 
        Parameter dictionary with all parameters not associated with MDA

    vals : dict
        Contains current state of simulation
    Returns
    -------
    dict 
        vals dictionary modified with vaccination state
    '''

    if not set(["ids"]).issubset(vals.keys()):
        vals["ids"] = np.array(range(len(vals['IndI'])))

    return vals


def Check_for_MDA_Vacc_And_Survey_Data(vals):
    '''
    Check if "n_treatments", "n_treatments_population", "n_surveys", "n_surveys_population" keys are in `vals`.
    These will store all the information of ages of treated and surveyed people
    If they are
    not then initialize for population
    
    Parameters
    ----------
    
    params : dict 
        Parameter dictionary with all parameters not associated with MDA

    vals : dict
        Contains current state of simulation
    Returns
    -------
    dict 
        vals dictionary modified with vaccination state
    '''

    if not set(["n_treatments", "n_treatments_population", "n_surveys", "n_surveys_population", "n_vaccinated", "n_vaccinated_population"]).issubset(vals.keys()):
        vals["n_treatments"] = {}
        vals["n_treatments_populations"] = {}
        vals["n_surveys"] = {}
        vals["n_surveys_population"] = {}
        vals["n_vaccinated_population"] = {}
        vals["n_vaccinated_population"] = {}

    return vals

def Check_and_init_vaccination_state(params,vals):
    '''
    Check if "vaccinated" and "time_since_vaccinated" keys are in `vals`. If they are
    not then initialize for population
    
    Parameters
    ----------
    
    params : dict 
        Parameter dictionary with all parameters not associated with MDA

    vals : dict
        Contains current state of simulation
    Returns
    -------
    dict 
        vals dictionary modified with vaccination state
    '''

    if not set(["vaccinated","time_since_vaccinated"]).issubset(vals.keys()):
        vals["vaccinated"] = np.zeros(params['N'],dtype=bool)
        vals["time_since_vaccinated"] = np.zeros(params['N'])

    return vals

def Check_and_init_MDA_treatment_state(params, vals, MDAData, numpy_state):
    '''
    Check if "treatProbability","MDA_coverage" and "sytematic_non_compliance" keys are in `vals`. If they are
    not then initialize for population
    
    Parameters
    ----------
    
    params : dict 
        Parameter dictionary with all parameters not associated with MDA

    vals : dict
        Contains current state of simulation
    Returns
    -------
    dict 
        vals dictionary modified with vaccination state
    '''
    np.random.set_state(numpy_state)
    if not set(["treatProbability","MDA_coverage", "systematic_non_compliance"]).issubset(vals.keys()):
        MDA_coverage = 0
        treatProbability = np.full(shape=params['N'], fill_value=np.nan, dtype=float)
        systematic_non_compliance = params['rho']
        vals["treatProbability"] = treatProbability
        if (len(MDAData) > 0):
            MDA_coverage = MDAData[0][3]
            vals["treatProbability"] = drawTreatmentProbabilities(params['N'], MDA_coverage, systematic_non_compliance)
        vals["MDA_coverage"] = MDA_coverage
        vals["systematic_non_compliance"] = systematic_non_compliance

    return vals

def init_ages(params, demog, numpy_state):

    '''
    Initialise age distribution
    Note: ages are in weeks.
    '''

    np.random.set_state(numpy_state)

    ages = np.arange(1, 1 + demog['max_age'])

    # ensure the population is in equilibrium
    propAges = np.empty(len(ages))
    propAges[:-1] = np.exp(-ages[:-1] / demog['mean_age']) - np.exp(-ages[1:] / demog['mean_age'])
    propAges[-1] = 1 - np.sum(propAges[:-1])

    return np.random.choice(a=ages, size=params['N'], replace=True, p=propAges)



def SecularTrendBetaDecrease(timesim, burnin, bet, params):
    simbeta = bet * np.ones(timesim + 1)
    if params['SecularTrendIndicator'] == 1:
        for j in range(round(burnin/52),round(len(simbeta)/52)):
            bet1 = simbeta[j * 52] 
            for i in range(52+1):
                simbeta[(j * 52) + i] = bet1 - (params['SecularTrendYearlyBetaDecrease'] * bet1 * i/52)
    return simbeta


def numMDAsBeforeNextSurvey(surveyPrev):
    '''
    Function to return the number of surveys before the next survey
    '''
    
    if surveyPrev >= 0.3:
        return 5 
    if surveyPrev >= 0.1:
        return 3
    if surveyPrev >= 0.05: 
        return 1
    return 100


def get_MDA_params(MDAData, MDA_round_current, vals):
    ageStart = MDAData[MDA_round_current][1]
    ageEnd = MDAData[MDA_round_current][2]
    cov = MDAData[MDA_round_current][3]
    label = MDAData[MDA_round_current][4]
    systematic_non_compliance = vals['systematic_non_compliance']
    return ageStart, ageEnd, cov, label, systematic_non_compliance

def check_if_we_need_to_redraw_probability_of_treatment(cov, systematic_non_compliance, vals):
    if(cov != vals['MDA_coverage'])| (systematic_non_compliance != vals['systematic_non_compliance']):
        editTreatProbability(vals, cov, systematic_non_compliance)
        vals['MDA_coverage'] = cov
        vals['systematic_non_compliance'] = systematic_non_compliance
    return vals

def update_MDA_information_for_output(MDAData, MDA_round_current, num_treated_people, vals, ageStart, ageEnd, nDoses, numMDA, coverage):
    nDoses[MDAData[MDA_round_current][-2]] += num_treated_people
                    # increment number of MDAs
    numMDA[MDAData[MDA_round_current][-2]] += 1
    coverage[MDAData[MDA_round_current][-2]] += num_treated_people / np.count_nonzero((vals['Age'] > ageStart * 52) & (vals['Age'] <= ageEnd * 52))
    return nDoses, numMDA, coverage

def sim_Ind_MDA_Include_Survey(params, vals, timesim, burnin,
                               demog, bet, MDA_times, MDAData,
                               vacc_times, VaccData, outputTimes, 
                               doSurvey, doIHMEOutput, numpy_state, distToUse  = "Poisson"):

    '''
    Function to run a single simulation with MDA at time points determined by function MDA_times.
    Output is true prevalence of infection/disease in children aged 1-9.
    '''
    outputTimes2 = copy.deepcopy(outputTimes)
    # when we are resuming previous simulations we use the provided random state
    np.random.set_state(numpy_state)

    #vacc_time = params['vacc_time']
    prevalence = []
    infections = []
    max_age = demog['max_age'] // 52 # max_age in weeks
    yearly_threshold_infs = np.zeros(( timesim+1, int(demog['max_age']/52)))
   # get initial prevalence in 1-9 year olds. will decide how many MDAs (if any) to do before another survey
    surveyPass = 0
    surveyTime = min(MDA_times) + (5 * 52) + 25
    nMDAWholePop = 0
    numMDAForSurvey = -1
    if doSurvey:
        surveyPrev, vals = returnSurveyPrev(vals, params['TestSensitivity'], params['TestSpecificity'], demog, 0, params['surveyCoverage'])

        # get a value for the number of MDAs to do before the next survey
        numMDAForSurvey = nMDAWholePop + numMDAsBeforeNextSurvey(surveyPrev)
        if surveyPrev <= 0.05:
            surveyTime = min(MDA_times) + 25
    
    
    nextOutputTime = min(outputTimes2)
    w = np.where(outputTimes2 == nextOutputTime)
    outputTimes2[w] = timesim + 10
    results = []
    
    vals['nSurvey'] = 0
    vals['prevNSurvey'] = 0
    
    
    nDoses = np.zeros(MDAData[0][-1], dtype=object)
    coverage = np.zeros(MDAData[0][-1], dtype=object)
    # initialize count of MDAs
    numMDA = np.zeros(MDAData[0][-1], dtype=object)
    prevNMDA = np.zeros(MDAData[0][-1], dtype=object)
    
    vals['numVacc'] = np.zeros(VaccData[0][-1], dtype=object)
    vals['nDosesVacc'] = np.zeros(VaccData[0][-1], dtype=object)
    vals['coverageVacc'] = np.zeros(VaccData[0][-1], dtype=object)
    vals['prevNVacc'] = np.zeros(VaccData[0][-1], dtype=object)
    
    doneSurveyThisYear = False # require this indicator so that we can output data for a survey even if 
    # no survey occurred in a year. Without this, we are likely to get outputs with different
    # number of rows in them for different simulations, as there may be different numbers of 
    # surveys based on the dynamics.
    betas = SecularTrendBetaDecrease(timesim, burnin, bet, params)

    for i in range( timesim):
        if i % 52 == 0:
            params['importation_rate'] *= params['importation_reduction_rate']

        if ((i+1) % 52) == 0:
            # if we are after the burnin and haven't done a survey this year, then do a survey with 0 coverage
            # so that it is stored in the output later.
            if doneSurveyThisYear == False and i > burnin:
                surveyPrev, vals = returnSurveyPrev(vals, params['TestSensitivity'], params['TestSpecificity'], demog, i/52, 0)
            doneSurveyThisYear = False

        if doIHMEOutput and i == nextOutputTime:
            
            # has the disease truly eliminated in the population
            true_elimination = 1 if (sum(vals['IndI']) + sum(vals['IndD'])) == 0 else 0
            # append the results to results variable
            results.append(outputResult(copy.deepcopy(vals), i, nDoses, coverage, numMDA-prevNMDA, 
                                        vals['nSurvey'] - vals['prevNSurvey'], surveyPass, true_elimination,
                                        vals['numVacc'] - vals['prevNVacc'], vals['nDosesVacc'] , vals['coverageVacc']))
            # when will next Endgame output time be
            nextOutputTime = min(outputTimes2)
            # change next output time location in the all output variable to be after the end of the simulation
            # then the next output will be done at the correct time
            w = np.where(outputTimes2 == nextOutputTime)
            outputTimes2[w] = timesim + 10
            # save current num surveys, num MDAS as previous num surveys/MDAs, so next output we can tell how many were performed
            # since last output
            vals['prevNSurvey'] = copy.deepcopy(vals['nSurvey']) 
            prevNMDA = copy.deepcopy(numMDA)
            vals['prevNVacc'] = copy.deepcopy(vals['numVacc']) 
            # set coverage and nDoses to 0, so that if these are non-zero, we know that they occured since last output
            nDoses = np.zeros(MDAData[0][-1], dtype=object)
            coverage = np.zeros(MDAData[0][-1], dtype=object)
            
            vals['nDosesVacc'] = np.zeros(VaccData[0][-1], dtype=object)
            vals['coverageVacc'] = np.zeros(VaccData[0][-1], dtype=object)
            
        if doSurvey and i == surveyTime:    
            surveyPrev, vals = returnSurveyPrev(vals, params['TestSensitivity'], params['TestSpecificity'], demog, i/52, params['surveyCoverage'])
            doneSurveyThisYear = True
            # if the prevalence is <= 5%, then we have passed the survey and won't do any more MDA
            if surveyPrev <= 0.05:
                surveyPass += 1
            else:
                surveyPass = 0

            # if we have passed 2 surveys, we won't do another one, so set the surveytime to be after simulation ends
            if surveyPass == 2:
                surveyTime = timesim + 10
            # if we have passed 1 survey, we will do another in 2 years time
            elif surveyPass == 1:
                surveyTime = i + 104  
            else: # if we didn't pass the survey, we will do another survey after a number of MDAs based on the prevalence. 
                # Assume that these MDAs must cover a significant portion of the population so call these nMDAWholePop.
                # add the number of MDAs already done to the number of MDAs to be done before the next survey
                numMDAForSurvey = nMDAWholePop + numMDAsBeforeNextSurvey(surveyPrev)
           
            vals['nSurvey'] += 1
        
        if i in MDA_times:
            MDA_round = np.where(MDA_times == i)[0]
            for l in range(len(MDA_round)):
                MDA_round_current = MDA_round[l]
                # we want to get the data corresponding to this MDA from the MDAdata
                ageStart, ageEnd, cov, label, systematic_non_compliance = get_MDA_params(MDAData, MDA_round_current, vals)
                if surveyPass >= 1:
                    cov = 0
                # if we have a non zero coverage and target people in an age range of at least 20 years
                # then class this as a whole population MDA and hence increment the nMDAWholePop by 1
                if ((ageEnd - ageStart) >= 20) and cov > 0:
                    nMDAWholePop += 1    
                # if cov or systematic non compliance have changed we need to re-draw the treatment probabilities
                # check if these have changed here, and if they have, then we re-draw the probabilities
                vals = check_if_we_need_to_redraw_probability_of_treatment(cov, systematic_non_compliance, vals)
                # do the MDA for the age range specified by ageStart and ageEnd
                vals, num_treated_people = MDA_timestep_Age_range(vals, params, ageStart, ageEnd, i/52, label, demog)
                # keep track of doses and coverage of the MDA to be output later.
                nDoses, numMDA, coverage = update_MDA_information_for_output(MDAData, MDA_round_current, num_treated_people,
                                                                                vals, ageStart, ageEnd, nDoses, numMDA, coverage)
                if nMDAWholePop == numMDAForSurvey and surveyPass < 2:
                    surveyTime = i + 25
                
                
        if i in vacc_times:
      
            vacc_round = np.where(vacc_times == i)[0]
            if(len(vacc_round) == 1):
                vacc_round = vacc_round[0]
                vals = vacc_timestep_Age_range(params, vals, vacc_round, VaccData, i/52, demog)
                
            else:
                for l in range(len(vacc_round)):
                    vacc_round2 = copy.deepcopy(vacc_round[l])
                    vals = vacc_timestep_Age_range(params, vals, vacc_round2, VaccData, i/52, demog)
                   
            #vals = vaccinate_population(vals = vals, params = params)
        #else:  removed and deleted one indent in the line below to correct mistake.
        #if np.logical_and(i == surveyTime, surveyPass==0):     
       
        vals = stepF_fixed(vals=vals, params=params, demog=demog, bet=betas[i], distToUse = distToUse)

        children_ages_1_9 = np.logical_and(vals['Age'] < 10 * 52, vals['Age'] >= 52)
        n_children_ages_1_9 = np.count_nonzero(children_ages_1_9)
        n_true_diseased_children_1_9 = np.count_nonzero(vals['IndD'][children_ages_1_9])
        n_true_infected_children_1_9 = np.count_nonzero(vals['IndI'][children_ages_1_9])
        prevalence.append(n_true_diseased_children_1_9 / n_children_ages_1_9)
        infections.append(n_true_infected_children_1_9 / n_children_ages_1_9)

        large_infection_count = (vals['No_Inf'] > params['n_inf_sev'])
        # Cast weights to integer to be able to count
        a, _ = np.histogram(vals['Age'], bins=max_age, weights=large_infection_count.astype(int))
        yearly_threshold_infs[i, :] = a / params['N']
        # check if time to save variables to make Endgame outputs
        

            
    vals['Yearly_threshold_infs'] = yearly_threshold_infs
    vals['True_Prev_Disease_children_1_9'] = prevalence # save the prevalence in children aged 1-9
    vals['True_Infections_Disease_children_1_9'] = infections # save the infections in children aged 1-9
    vals['State'] = np.random.get_state() # save the state of the simulations

    return vals, results




def returnSurveyPrev(vals, TestSensitivity, TestSpecificity, demog, t, surveyCoverage = 1):
    '''
    Function to run a return the tested prevalence of 1-9 year olds.
    This includes sensitivity and specificity of the test.
    Will be used in surveying to decide if we should do MDA, and how many MDAs before next test
    '''
    # survey 1-9 year olds
    children_ages_1_9 = np.logical_and(vals['Age'] < 10 * 52, vals['Age'] >= 52)

    # Draw random uniform numbers between 0 and 1 for each individual
    random_draw = np.random.uniform(0, 1, size = len(vals['Age']))

    # Combine conditions: children ages 1-9 and random draw below surveyCoverage
    surveyed_children  = np.logical_and(children_ages_1_9, random_draw < surveyCoverage)

    # calculate true number of diseased 1-9 year olds
    Diseased = vals['IndD'][surveyed_children].sum()

    # how many 1-9 year olds are not diseased
    NonDiseased = surveyed_children.sum() - Diseased

    # perform test with given sensitivity and specificity to get test positives
    positive = int(np.random.binomial(n=Diseased, size=1, p = TestSensitivity)) + int(np.random.binomial(n=NonDiseased, size=1, p = 1- TestSpecificity)) 
    if t > 0:
        n_surveys_by_age, _ = np.histogram(
                    vals['Age'][surveyed_children]/52,
                    bins=np.arange(0, int(demog['max_age']/52) + 1),
                )
        
        n_people_by_age, _ = np.histogram(
                    vals['Age']/52,
                    bins=np.arange(0, int(demog['max_age']/52) + 1),
                )
        # add this to the SD n survey population dict
        vals["n_surveys_population"][
                    str(t) + ", surveys"
                ] = n_people_by_age
        vals["n_surveys"][
                    str(t) + ", surveys"
                ] = n_surveys_by_age
    if surveyCoverage == 0:
        return 0, vals
    else:
        # return prevalence,calculated as number who tested positive divided by number of 1-9 year olds
        return positive/surveyed_children.sum(), vals



def getResultsNTDMC(results, Start_date, burnin):
    '''
    Function to collate results for NTDMC
    '''

    
    for i in range(len(results)):
        d = copy.deepcopy(results[i][0])
        prevs = np.array(d['True_Prev_Disease_children_1_9']) 
        start = burnin # get prevalence from the end of the burnin onwards
        step = 52 # step forward 52 weeks
        chosenPrevs = prevs[start::step] 
        if i == 0:
           df = pd.DataFrame(0, range(len(chosenPrevs)), columns= range(len(results)+4))
           df = df.rename(columns={0: "Time", 1: "age_start", 2: "age_end", 3: "measure"}) 
           df.iloc[:, 0] = range(Start_date.year, Start_date.year + len(chosenPrevs))
           df.iloc[:, 1] = np.repeat(1, len(chosenPrevs))
           df.iloc[:, 2] = np.repeat(9, len(chosenPrevs))
           df.iloc[:, 3] = np.repeat("prevalence", len(chosenPrevs))
        df.iloc[:,i+4] = chosenPrevs
    for i in range(len(results)):
        df = df.rename(columns={i+4: "draw_"+ str(i)}) 
    return df

def getResultsIHME(results, demog, params, outputYear):
    '''
    Function to collate results for IHME
    '''
    max_age = demog['max_age'] // 52 # max_age in weeks

    df = pd.DataFrame(0, range(len(outputYear)*4*60 + len(outputYear)*2 ), columns= range(len(results)+4))
    df = df.rename(columns={0: "Time", 1: "age_start", 2: "age_end", 3: "measure"}) 
    
    for i in range(len(results)):
        ind = 0
        d = copy.deepcopy(results[i][1])
        for j in range(len(d)):
            year = outputYear[j]
            large_infection_count = (d[j].NoInf > params['n_inf_sev'])
            infection_count = (d[j].IndI > 0)
            Diseased = np.where(d[j].IndD == 1)
            NonDiseased = np.where(d[j].IndD == 0)
            pos = np.zeros(len(d[j].Age), dtype = object)
            if(len(Diseased) > 0):
                TruePositive = np.random.binomial(n=1, size=len(Diseased[0]), p = params['TestSensitivity'])
                pos[Diseased] = TruePositive
            if(len(NonDiseased) > 0):
                FalsePositive = np.random.binomial(n=1, size=len(NonDiseased[0]), p = 1- params['TestSpecificity'])
                pos[NonDiseased] = FalsePositive
            
 
            Age = d[j].Age
            # Cast weights to integer to be able to count
            manyInfs, _ = np.histogram(Age, bins=max_age, weights=large_infection_count.astype(int))
            Infs, _ = np.histogram(Age, bins=max_age, weights=infection_count.astype(int))
            nums, _ = np.histogram(Age, bins=max_age)
            observedDis, _ = np.histogram(Age, bins=max_age, weights=pos.astype(int))
            k = np.where(nums == 0)
            nums[k] = 1
            if i == 0:
                df.iloc[range(ind, ind+max_age), 0] = np.repeat(year,max_age)
                df.iloc[range(ind, ind+max_age), 1] = range(0, max_age)
                df.iloc[range(ind, ind+max_age), 2] = range(1, max_age + 1)
                df.iloc[range(ind, ind+max_age), 3] = np.repeat("TruePrevalence", max_age)
                df.iloc[range(ind, ind+max_age), i+4] = Infs/nums
                ind += max_age
                df.iloc[range(ind, ind+max_age), 0] = np.repeat(year,max_age)
                df.iloc[range(ind, ind+max_age), 1] = range(0, max_age)
                df.iloc[range(ind, ind+max_age), 2] = range(1, max_age + 1)
                df.iloc[range(ind, ind+max_age), 3] = np.repeat("ObservedTF", max_age)
                df.iloc[range(ind, ind+max_age), i+4] = observedDis/nums
                ind += max_age
                df.iloc[range(ind, ind+max_age), 0] = np.repeat(year,max_age)
                df.iloc[range(ind, ind+max_age), 1] = range(0, max_age)
                df.iloc[range(ind, ind+max_age), 2] = range(1, max_age + 1)
                df.iloc[range(ind, ind+max_age), 3] = np.repeat("heavyInfections", max_age)
                df.iloc[range(ind, ind+max_age), i+4] = manyInfs/nums
                ind += max_age
                nums[k] = 0
                df.iloc[range(ind, ind+max_age), 0] = np.repeat(year,max_age)
                df.iloc[range(ind, ind+max_age), 1] = range(0, max_age)
                df.iloc[range(ind, ind+max_age), 2] = range(1, max_age + 1)
                df.iloc[range(ind, ind+max_age), 3] = np.repeat("number", max_age)
                df.iloc[range(ind, ind+max_age), i+4] = nums
                ind += max_age
                df.iloc[ind, 0] = year
                df.iloc[ind, 3] = "nSurvey"
                df.iloc[ind, 1] = "None"
                df.iloc[ind, 2] = "None"
                df.iloc[ind, i+4] = d[j].nSurvey
                ind += 1
                df.iloc[ind, 0] = year
                df.iloc[ind, 3] = "surveyPass"
                df.iloc[ind, 1] = "None"
                df.iloc[ind, 2] = "None"
                df.iloc[ind, i+4] = d[j].surveyPass
                ind += 1
            else:
                df.iloc[range(ind, ind+max_age), i+4] = Infs/nums
                ind += max_age
                df.iloc[range(ind, ind+max_age), i+4] = observedDis/nums
                ind += max_age
                df.iloc[range(ind, ind+max_age), i+4] = manyInfs/nums
                ind += max_age
                df.iloc[range(ind, ind+max_age), i+4] = nums
                ind += max_age
                df.iloc[ind, i+4] = d[j].nSurvey
                ind += 1
                df.iloc[ind, i+4] = d[j].surveyPass
                ind += 1
    for i in range(len(results)):
        df = df.rename(columns={i+4: "draw_"+ str(i)}) 
    return df


def getMDAInfo(res, Start_date, sim_params, demog):
    max_age = demog['max_age'] // 52 # max_age in weeks

    d = None

    max_age = demog['max_age'] // 52 # max_age in weeks
    for i in range(len(res)):
        out = copy.deepcopy(res[i][0])
        mdaCount = 1
        count = 0
        previousT = -1 # we want to keep track of the number of MDA rounds per year, so keep track of the time of 
        # the last MDA. Initialize this at -1 as no MDA's will take place then, so we will update correctly for first MDA
        for key, value in out['n_treatments'].items():
            #print(key)
            t = math.floor(float(key.split(",")[0]))
            t = math.floor(Start_date.year - sim_params['burnin']/52 + t)
            if t != previousT:
                MDAroundNumber = 1
                previousT = t
            else:
                MDAroundNumber += 1
            measure = str(key.split(",")[1])
            if i == 0:
                newrows = pd.DataFrame(
                        {
                            "Time": np.repeat(t, len(value)),
                            "age_start": range(int(max_age)),
                            "age_end": range(1, 1 + int(max_age)),
                            "measure": np.repeat(measure + " round " + str(MDAroundNumber), len(value)),
                            "draw_0": value,
                        }
                    )
            else:
                 newrows = pd.DataFrame(
                        {
                            "draw_0": value,
                        }
                    )
            
            if count == 0:
                    count += 1
                    d = newrows
            else:
                    assert d is not None
                    count += 1
                    d = pd.concat([d, newrows], ignore_index = True)
                
            value = out['n_treatments_population'][key]
            
            if i == 0:
                newrows = pd.DataFrame(
                        {
                            "Time": np.repeat(t, len(value)),
                            "age_start": range(int(max_age)),
                            "age_end": range(1, 1 + int(max_age)),
                            "measure": np.repeat(measure + " round " + str(MDAroundNumber) + " population", len(value)),
                            "draw_0": value,
                        }
                    )
            else:
                newrows = pd.DataFrame(
                        {
                            "draw_0": value,
                        }
                    )
            mdaCount += 1
            d = pd.concat([d, newrows], ignore_index = True)
            
            if count == len(out['n_treatments'].items()):
                if i == 0:
                    output = d
                else:
                    cname = 'draw_' + str(i)
                    output[cname] = d
    
    return output


def getVaccInfo(res, Start_date, sim_params, demog):
    max_age = demog['max_age'] // 52 # max_age in weeks

    d = None

    for i in range(len(res)):
        out = copy.deepcopy(res[i][0])
        vaccCount = 1
        count = 0
        previousT = -1 # we want to keep track of the number of vaccination rounds per year, so keep track of the time of 
        # the last vaccination. Initialize this at -1 as no vaccination 's will take place then, so we will update correctly for first vaccination 
        if len(out['n_vaccinated'].items()) == 0:
            return {}
        for key, value in out['n_vaccinated'].items():
            #print(key)
            t = math.floor(float(key.split(",")[0]))
            t = math.floor(Start_date.year - sim_params['burnin']/52 + t)
            if t != previousT:
                VaccRoundNumber = 1
                previousT = t
            else:
                VaccRoundNumber += 1
            measure = str(key.split(",")[1])
            if i == 0:
                newrows = pd.DataFrame(
                        {
                            "Time": np.repeat(t, len(value)),
                            "age_start": range(int(max_age)),
                            "age_end": range(1, 1 + int(max_age)),
                            "measure": np.repeat(measure + " round " + str(VaccRoundNumber), len(value)),
                            "draw_0": value,
                        }
                    )
            else:
                 newrows = pd.DataFrame(
                        {
                            "draw_0": value,
                        }
                    )
            
            if count == 0:
                    count += 1
                    d = newrows
            else:
                    assert d is not None
                    count += 1
                    d = pd.concat([d, newrows], ignore_index = True)

            value = out['n_vaccinated_population'][key]

            if i == 0:
                newrows = pd.DataFrame(
                        {
                            "Time": np.repeat(t, len(value)),
                            "age_start": range(int(max_age)),
                            "age_end": range(1, 1 + int(max_age)),
                            "measure": np.repeat(measure + " round " + str(VaccRoundNumber) + " population", len(value)),
                            "draw_0": value,
                        }
                    )
            else:
                newrows = pd.DataFrame(
                        {
                            "draw_0": value,
                        }
                    )
            vaccCount += 1
            d = pd.concat([d, newrows], ignore_index = True)

            if count == len(out['n_vaccinated'].items()):
                if i == 0:
                    output = d
                else:
                    cname = 'draw_' + str(i)
                    output[cname] = d

    return output


def getSurveyInfo(res, Start_date, sim_params, demog):

    d = None

    max_age = demog['max_age'] // 52 # max_age in weeks
    for i in range(len(res)):
        out = copy.deepcopy(res[i][0])
        mdaCount = 1
        count = 0
        for key, value in out['n_surveys'].items():
            t = math.floor(float(key.split(",")[0]))
            if t > 0:
                t = math.floor(Start_date.year - sim_params['burnin']/52 + t)
                measure = str(key.split(",")[1])
                if i == 0:
                    newrows = pd.DataFrame(
                            {
                                "Time": np.repeat(t, len(value)),
                                "age_start": range(int(max_age)),
                                "age_end": range(1, 1 + int(max_age)),
                                "measure": np.repeat(measure, len(value)),
                                "draw_0": value,
                            }
                        )
                else:
                    newrows = pd.DataFrame(
                            {
                                "draw_0": value,
                            }
                        )
                
                if count == 0:
                        count += 1
                        d = newrows
                else:
                        assert d is not None
                        count += 1
                        d = pd.concat([d, newrows], ignore_index = True)
                    
                value = out['n_surveys_population'][key]
                
                if i == 0:
                    newrows = pd.DataFrame(
                            {
                                "Time": np.repeat(t, len(value)),
                                "age_start": range(int(max_age)),
                                "age_end": range(1, 1 + int(max_age)),
                                "measure": np.repeat(measure + " population", len(value)),
                                "draw_0": value,
                            }
                        )
                else:
                    newrows = pd.DataFrame(
                            {
                                "draw_0": value,
                            }
                        )
                mdaCount += 1
                d = pd.concat([d, newrows], ignore_index = True)

                if key == list(out['n_surveys'].keys())[-1]:
                    if i == 0:
                        output = d
                    else:
                        cname = 'draw_' + str(i)
                        output[cname] = d
        
    return output

def combineIHME_MDA_SurveyData(results, demog, params, outputYear, Start_date, sim_params):
    IHME = getResultsIHME(results, demog, params, outputYear)
    MDA = getMDAInfo(results, Start_date, sim_params, demog)
    Vacc = getVaccInfo(results, Start_date, sim_params, demog)
    Survey = getSurveyInfo(results, Start_date, sim_params, demog)
    if len(MDA) > 0:
        IHME = pd.concat([IHME, MDA], ignore_index = True)
    if len(Vacc) > 0:
        IHME = pd.concat([IHME, Vacc], ignore_index = True)
    if len(Survey) > 0:
        IHME = pd.concat([IHME, Survey], ignore_index = True)
    return  IHME


def getInterventionAgeRanges(coverageFileName, intervention, data_path=None):
    PlatCov = pd.read_csv(
        _validate_data_path(data_path) / coverageFileName
    )
    InterventionRows = np.where(PlatCov.Platform == intervention)[0]
    PlatCov = PlatCov.iloc[InterventionRows, :]
    InterventionAgeRanges = np.zeros([PlatCov.shape[0],2], dtype = object)
    minAgeIndex = np.where(PlatCov.columns == "min age")[0][0]
    maxAgeIndex = np.where(PlatCov.columns == "max age")[0][0]
    for i in range(PlatCov.shape[0]):
        InterventionAgeRanges[i, 0] = PlatCov.iloc[i, minAgeIndex]
        InterventionAgeRanges[i, 1] = PlatCov.iloc[i, maxAgeIndex]
        
    return InterventionAgeRanges

def getResultsIPM(results, demog, params, outputYear, MDAAgeRanges, VaccAgeRanges):
    '''
    Function to collate results for IPM
    '''
   
    df = pd.DataFrame(0, range(len(outputYear)*3 + len(outputYear) * 3 * len(MDAAgeRanges) + len(outputYear) * 3 * len(VaccAgeRanges)), 
                      columns= range(len(results)+4))
    df = df.rename(columns={0: "Time", 1: "age_start", 2: "age_end", 3: "measure"}) 
    
    for i in range(len(results)):
        ind = 0
        d = copy.deepcopy(results[i][1])
        for j in range(len(d)):
            year = outputYear[j]
            
            if i == 0:
                df.iloc[ind, 0] = year
                df.iloc[ind, 3] = "nSurvey"
                df.iloc[ind, 1] = "None"
                df.iloc[ind, 2] = "None"
                df.iloc[ind, i+4] = d[j].nSurvey
                ind += 1
                df.iloc[ind, 0] = year
                df.iloc[ind, 3] = "surveyPass"
                df.iloc[ind, 1] = "None"
                df.iloc[ind, 2] = "None"
                df.iloc[ind, i+4] = d[j].surveyPass
                ind += 1
                df.iloc[ind, 0] = year
                df.iloc[ind, 3] = "trueElimination"
                df.iloc[ind, 1] = "None"
                df.iloc[ind, 2] = "None"
                df.iloc[ind, i+4] = d[j].elimination
                ind += 1
                for k in range(len(MDAAgeRanges)):
                    df.iloc[ind, 0] = year
                    df.iloc[ind, 3] = "nDosesMDA"
                    df.iloc[ind, 1] = MDAAgeRanges[k][0]
                    df.iloc[ind, 2] = MDAAgeRanges[k][1]
                    df.iloc[ind, i+4] = d[j].nMDADoses[k]
                    ind += 1
                    df.iloc[ind, 0] = year
                    df.iloc[ind, 3] = "MDAcoverage"
                    df.iloc[ind, 1] = MDAAgeRanges[k][0]
                    df.iloc[ind, 2] = MDAAgeRanges[k][1]
                    df.iloc[ind, i+4] = d[j].propMDA[k]
                    ind += 1
                    df.iloc[ind, 0] = year
                    df.iloc[ind, 3] = "numMDAs"
                    df.iloc[ind, 1] = MDAAgeRanges[k][0]
                    df.iloc[ind, 2] = MDAAgeRanges[k][1]
                    df.iloc[ind, i+4] = d[j].nMDA[k]
                    ind += 1
                for k in range(len(VaccAgeRanges)):
                    df.iloc[ind, 0] = year
                    df.iloc[ind, 3] = "nDosesVacc"
                    df.iloc[ind, 1] = VaccAgeRanges[k][0]
                    df.iloc[ind, 2] = VaccAgeRanges[k][1]
                    df.iloc[ind, i+4] = d[j].nVaccDoses[k]
                    ind += 1
                    df.iloc[ind, 0] = year
                    df.iloc[ind, 3] = "VaccCoverage"
                    df.iloc[ind, 1] = VaccAgeRanges[k][0]
                    df.iloc[ind, 2] = VaccAgeRanges[k][1]
                    df.iloc[ind, i+4] = d[j].propVacc[k]
                    ind += 1
                    df.iloc[ind, 0] = year
                    df.iloc[ind, 3] = "numVaccs"
                    df.iloc[ind, 1] = VaccAgeRanges[k][0]
                    df.iloc[ind, 2] = VaccAgeRanges[k][1]
                    df.iloc[ind, i+4] = d[j].nVacc[k]
                    ind += 1
                    
                
            else:
                df.iloc[ind, i+4] = d[j].nSurvey
                ind += 1
                df.iloc[ind, i+4] = d[j].surveyPass
                ind += 1
                df.iloc[ind, i+4] = d[j].elimination
                ind += 1
                for k in range(len(MDAAgeRanges)):               
                    df.iloc[ind, i+4] = d[j].nMDADoses[k]
                    ind += 1   
                    df.iloc[ind, i+4] = d[j].propMDA[k]
                    ind += 1
                    df.iloc[ind, i+4] = d[j].nMDA[k]
                    ind += 1
                for k in range(len(VaccAgeRanges)):               
                    df.iloc[ind, i+4] = d[j].nVaccDoses[k]
                    ind += 1   
                    df.iloc[ind, i+4] = d[j].propVacc[k]
                    ind += 1
                    df.iloc[ind, i+4] = d[j].nVacc[k]
                    ind += 1
                
    for i in range(len(results)):
        df = df.rename(columns={i+4: "draw_"+ str(i)}) 
    return df

def resetMDAVaccAndSurveyData(vals):
    '''
    reset the MDA and survey data before running a simulation
    '''

    vals["n_treatments"] = {}
    vals["n_treatments_population"] = {}
    vals["n_surveys"] = {}
    vals['n_surveys_population'] = {}
    vals['n_vaccinated'] = {}
    vals['n_vaccinated_population'] = {}

    return vals

def run_single_simulation(pickleData, params, timesim, burnin, demog, beta, MDA_times, MDAData, vacc_times, VaccData,
                          outputTimes, doSurvey, doIHMEOutput, index, numpy_state, distToUse = "Poisson"):

    '''
    Function to run a single instance of the simulation. The starting point for these simulations
    is
    '''
    vals = copy.deepcopy(pickleData)
    vals = Check_and_init_vaccination_state(params,vals)
    vals = Check_and_init_MDA_treatment_state(params, vals, MDAData, numpy_state)
    vals = Check_for_IDs(vals)
    vals = Check_for_MDA_Vacc_And_Survey_Data(vals)
    vals = resetMDAVaccAndSurveyData(vals)
    params['N'] = len(vals['IndI'])
    results = sim_Ind_MDA_Include_Survey(params=params,
                                        vals = vals, timesim = timesim,
                                        burnin=burnin,
                                        demog=demog, bet=beta, MDA_times = MDA_times, 
                                        MDAData=MDAData, vacc_times = vacc_times, VaccData = VaccData,
                                        outputTimes= outputTimes, doSurvey=doSurvey, doIHMEOutput=doIHMEOutput,
                                        numpy_state=numpy_state, distToUse= distToUse)
    return results

def seed_to_state(seed):
    np.random.seed(seed)
    return np.random.get_state()

##########################################################################################
##########################################################################################
##########################################################################################
##########################################################################################





