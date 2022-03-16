import behavioral_data
import fiber_data
from fp_utils import FiberPhotopy

import numpy as np
import pandas as pd
from math import ceil
import matplotlib.pyplot as plt
from scipy import integrate,stats,signal
#from scipy.stats import sem

class RatSession(FiberPhotopy):
    """Create object containing both fiber recordings and behavioral files from a single session."""

    def __init__(self,behavior,fiber,rat_ID=None,folder=None,**kwargs):
        super().__init__('all',**kwargs)
        self.rat_ID = rat_ID
        if type(behavior) == behavioral_data.BehavioralData:
            self.behavior = behavior
        else:
            self.behavior = behavioral_data.BehavioralData(behavior)
        if type(fiber) == fiber_data.FiberData:
            if fiber.alignement == self.behavior.rec_start:
                self.fiber = fiber
            else:
                self.fiber = fiber_data.FiberData(fiber.filepath,alignement=self.behavior.rec_start)
        else:
            self.fiber = fiber_data.FiberData(fiber,alignement=self.behavior.rec_start)
        self.analyses = {}
        self.analyzable_events = self.behavior.events(recorded=True,window=self.default_window)
        self.recorded_intervals = self.behavior.intervals(recorded=True,window=self.default_window)

    def _sample(self,time_array,event_time,window):
        """Take a sample of the recording, based on one event and desired preevent and postevent duration."""
        start  = event_time - window[0]
        end    = event_time + window[1]
        start_idx = np.where(abs(time_array -      start) == min(abs(time_array -      start)))[0][0]
        event_idx = np.where(abs(time_array - event_time) == min(abs(time_array - event_time)))[0][0]
        end_idx   = np.where(abs(time_array -        end) == min(abs(time_array -        end)))[0][-1]
        return (start_idx , event_idx, end_idx)        
        
        
    def analyze_perievent(self,
                          event_time,
                          window     = 'default',
                          norm       = 'F'):
        """Return Analysis object, related to defined perievent window."""
        res = Analysis(self.rat_ID)
        res.event_time     = event_time
        res.fiberfile      = self.fiber.filepath
        res.behaviorfile   = self.behavior.filepath
        if norm == 'default':
            res.normalisation = self.default_norm
        else:
            try:
                res.normalisation   = {'F' : 'delta F/F', 'Z' : 'Z-scores'}[norm]
            except KeyError:
                print("Invalid choice for signal normalisation !\nZ-score differences: norm='Z'\ndelta F/f: stand='F'")
                return None
        res.event_time = event_time
        try:
            res.rec_number = self.fiber._find_rec(event_time)[0] # locates recording containing the timestamp
        except IndexError:
            print('No fiber recording at this timestamp')
            return None
        if window == 'default':
            res.window    = self.default_window
        else:
            res.window    = window
        res.recordingdata = self.fiber.norm(rec=res.rec_number,method=norm)
        res.rawdata       = self.fiber.norm(rec=res.rec_number,method='raw')
        start_idx,event_idx,end_idx = self._sample(res.recordingdata[:,0],event_time,res.window)
        res.data          = res.recordingdata[start_idx:end_idx+1]
        res.raw_signal    = res.rawdata[start_idx:end_idx+1][:,1]
        res.raw_control   = res.rawdata[start_idx:end_idx+1][:,2]
        res.signal        = res.data[:,1]
        res.time          = res.data[:,0]
        res.sampling_rate = 1/np.diff(res.time).mean()
        res.postevent     = res.data[end_idx-event_idx:][:,1]
        res.pre_raw_sig   = res.raw_signal[:end_idx-event_idx]
        res.post_raw_sig  = res.raw_signal[end_idx-event_idx:]
        res.post_raw_ctrl = res.raw_control[end_idx-event_idx:]
        res.post_time     = res.data[end_idx-event_idx:][:,0]
        res.preevent      = res.data[:end_idx-event_idx][:,1]
        res.pre_time      = res.data[:end_idx-event_idx][:,0]
        res.zscores       = (res.signal - res.preevent.mean()) / res.preevent.std()
        res.pre_zscores   = res.zscores[:end_idx-event_idx]
        res.post_zscores  = res.zscores[end_idx-event_idx:]
        res.rob_zscores   = (res.signal - np.median(res.preevent))/stats.median_abs_deviation(res.preevent)
        res.pre_Rzscores  = res.rob_zscores[:end_idx-event_idx]
        res.post_Rzscores = res.rob_zscores[end_idx-event_idx:]
        res.preAVG_Z      = res.pre_zscores.mean()
        res.postAVG_Z     = res.post_zscores.mean()
        res.preAVG_RZ     = res.pre_Rzscores.mean()
        res.postAVG_RZ    = res.post_Rzscores.mean()
        res.pre_raw_AUC   = integrate.simpson(res.pre_raw_sig, res.pre_time)
        res.post_raw_AUC  = integrate.simpson(res.post_raw_sig, res.post_time)
        res.preAUC        = integrate.simpson(res.preevent, res.pre_time)
        res.postAUC       = integrate.simpson(res.postevent, res.post_time)
        res.preZ_AUC      = integrate.simpson(res.pre_zscores, res.pre_time)
        res.postZ_AUC     = integrate.simpson(res.post_zscores, res.post_time)
        res.preRZ_AUC     = integrate.simpson(res.pre_Rzscores, res.pre_time)
        res.postRZ_AUC    = integrate.simpson(res.post_Rzscores, res.post_time)
        self.analyses.update({f'rec{res.rec_number}_{res.event_time}_{res.window}' : res})
        return res

    def update_window(self,new_window):
        """Change perievent window."""
        self.default_window     = new_window
        self.analyzable_events  = self.behavior.events(recorded=True,window=self.default_window)
        self.recorded_intervals = self.behavior.intervals(recorded=True,window=self.default_window)
            
    def plot(self,what='events'):
        """Plot either events or intervals that happen within recording timeframe."""
        if what == 'events':
            data = {k:v for k,v in self.analyzable_events.items() if v.size>0}
        elif what == 'intervals':
            data = {k:v for k,v in self.recorded_intervals.items() if v.size>0}
        else:
            print("Choose either 'intervals' or 'events'")
        self.behavior.figure(obj=list(data.values()),label_list=list(data.keys()))

class Analysis:
    """Give results of perievent analysis relative to one event from a session."""

    def __init__(self,rat_ID):
        """Initialize Analysis object."""
        super().__init__()

    def __repr__(self):
        """Represent Analysis. Show attributes."""
        return '\n'.join(['<obj>.'+i for i in self.__dict__.keys()])

    def plot(self,
             data,
             ylabel      = None,
             xlabel      = 'time',
             plot_title  = None,
             figsize     = (20,10),
             event       = True,
             event_label = 'event',
             linewidth   = 2,
             smooth      = 'savgol',
             smth_window = 'default'):
        """Visualize data, by default smoothes data with Savitski Golay filter (window size 250ms)."""
        try:
            data = self.__dict__[data]
        except KeyError:
            print(f'Input type should be a string, possible inputs:\n{self._possible_data()}')
        time = self.time
        if smooth:
            time_and_data = self.smooth(data,method=smooth,window=smth_window)
            time = time_and_data[:,0]
            data = time_and_data[:,1]
        if len(data) == len(time):
            fig = plt.figure(figsize=figsize)
            plt.plot(time,data,c='r')
            plt.xlabel = xlabel
            plt.ylabel = ylabel
            plt.suptitle(plot_title)
            if event:
                plt.axvline(self.event_time,c='k',label=event_label,lw=linewidth)

    def _possible_data(self):
        d = {k:v for k,v in self.__dict__.items() if type(v) == np.ndarray}
        l = [f"'{k}'" for k in d.keys() if len(d[k]) == len(self.time)]
        return '\n'.join(l)

    def smooth(self,
               data,
               method    = 'savgol',
               window    = 'default',
               polyorder = 3,
               add_time  = True):
        """Return smoothed data, possible methods: Savitsky-Golay filter, rolling average."""
        if type(data) == str:
            data = self.__dict__[data]
        if type(window) == str:
            if window[-2:] == 'ms':
                window = ceil(float(window[:-2])/1000 * self.sampling_rate)
            if window == 'default':
                window = ceil(self.sampling_rate/4) #250 ms
        if method == 'savgol':
            if window%2 ==0: window += 1
            smoothed = signal.savgol_filter(data,window,polyorder)
            if add_time:
                return np.vstack((self.time,
                                  smoothed)).T
        if method == 'rolling':
            smoothed = pd.Series(data).rolling(window=window).mean().iloc[window-1:].values
            if add_time:
                return np.vstack((pd.Series(self.time).rolling(window=window).mean().iloc[window-1:].values,
                                  smoothed)).T
        return smoothed


class MultiAnalysis(FiberPhotopy):
    """Group analyses or multiple events for single subject."""

    def __init__(self,rat_session_list):
        super().__init__(self)

# find similar timestamps

#
