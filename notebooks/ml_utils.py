import pandas as pd

# Combine all data in one dataframe
from sklearn import preprocessing
encoder = preprocessing.LabelEncoder() 
from sklearn.preprocessing import MinMaxScaler
import pandas as pd
from test_utils import combine_data
import ipywidgets as widgets

from keras.models import Sequential
from keras.layers import Dense, Activation, LSTM, Dropout
import matplotlib.pyplot as plot

from sklearn.metrics import r2_score, median_absolute_error
from sklearn.metrics import mean_absolute_error, mean_squared_error#, mean_squared_log_error 

from numpy import concatenate
from math import sqrt

from formula_utils import exponential_smoothing

def series_to_supervised(data, n_in=1, n_out=1, dropnan=True):
	n_vars = 1 if type(data) is list else data.shape[1]
	df = pd.DataFrame(data)
	cols, names = list(), list()
	# input sequence (t-n, ... t-1)
	for i in range(n_in, 0, -1):
		cols.append(df.shift(i))
		names += [('var%d(t-%d)' % (j+1, i)) for j in range(n_vars)]
	# forecast sequence (t, t+1, ... t+n)
	for i in range(0, n_out):
		cols.append(df.shift(-i))
		if i == 0:
			names += [('var%d(t)' % (j+1)) for j in range(n_vars)]
		else:
			names += [('var%d(t+%d)' % (j+1, i)) for j in range(n_vars)]
	# put it all together
	agg = pd.concat(cols, axis=1)
	agg.columns = names
	# drop rows with NaN values
	if dropnan:
		agg.dropna(inplace=True)
	return agg

def prep_dataframe_ML(dataframeModel, min_date, max_date, list_features, n_lags, ratio_train, alpha_filter, reference_name, verbose = True):

    ## Trim dates
    dataframeModel = dataframeModel[dataframeModel.index > min_date]
    dataframeModel = dataframeModel[dataframeModel.index < max_date]
        
    # get selected values from list
    dataframeSupervised = dataframeModel.loc[:,list_features]
    dataframeSupervised = dataframeSupervised.dropna()

    # Training periods
    total_len = len(dataframeSupervised.index)
    n_train_periods = int(round(total_len*ratio_train))

    if alpha_filter<1:
        for column in dataframeSupervised.columns:
            dataframeSupervised[column] = exponential_smoothing(dataframeSupervised[column], alpha_filter)
    
    index = dataframeSupervised.index
    values = dataframeSupervised.values

    n_features = len(list_features) - 1
    n_obs = n_lags * n_features
    # print 'n_features {}'.format(n_features)
    # print 'n_obs {}'.format(n_obs)
    
    ## Option sensor 1 (lag 1 and no lagged prediction as feature)
    reframed = series_to_supervised(values, n_lags, 1)
    
    # drop columns we don't want
    if n_lags == 1:
        reframed = reframed.iloc[:,1:-n_features]
        n_predicted_features= 1
    else:
        # reframed_drop = reframed.iloc[:,1:]
        reframed.drop(reframed.columns[range(0,(n_features+1)*n_lags,n_features+1)], axis=1, inplace=True)
        reframed.drop(reframed.columns[range(n_obs+1, n_obs+n_features+1)], axis=1, inplace=True)
        n_predicted_features = 1
        
    values_drop = reframed.values

    scaler = MinMaxScaler(feature_range=(0, 1))
    scaled = scaler.fit_transform(values_drop)

    # split into train and test sets
    train = scaled[:n_train_periods, :]
    test = scaled[n_train_periods:, :]

    # split into input and outputs
    train_X, train_y = train[:, :-n_predicted_features], train[:, -n_predicted_features]
    test_X, test_y = test[:, :-n_predicted_features], test[:, -n_predicted_features]

    # print 'Training X, y and Test X, y shapes before reshaping'
    # print (train_X.shape, train_y.shape, test_X.shape, test_y.shape)

    # reshape input to be 3D [samples, timesteps, features]
    train_X = train_X.reshape((train_X.shape[0], n_lags, n_features))
    test_X = test_X.reshape((test_X.shape[0], n_lags, n_features))
    # print 'Training X, y and Test X, y shapes after reshaping'
    # print (train_X.shape, train_y.shape, test_X.shape, test_y.shape)
    
    if verbose:
    	print 'DataFrame has been reframed and prepared for supervised learning'
    	print 'Reference is: {}'.format(reference_name)
    	print 'Features are: {}'.format([i for i in list_features[1:]])
    	print 'Traning X Shape {}, Training Y Shape {}, Test X Shape {}, Test Y Shape {}'.format(train_X.shape, train_y.shape, test_X.shape, test_y.shape)
    
    return index, train_X, train_y, test_X, test_y, scaler, n_train_periods

def fit_model_ML(train_X, train_y, test_X, test_y, epochs = 50, batch_size = 72, verbose = 2, plotResult = True, loss = 'mse', optimizer = 'adam'):
    
    model = Sequential()
    layers = [100, 100, 100, 1]
    model.add(LSTM(layers[0], return_sequences=True, input_shape=(train_X.shape[1], train_X.shape[2])))
    model.add(Dropout(0.2))
    model.add(LSTM(layers[1], return_sequences=True))
    model.add(LSTM(layers[2], return_sequences=False))
    model.add(Dropout(0.2))
    model.add(Dense(output_dim=layers[3]))
    model.add(Activation("linear"))

    model.compile(loss=loss, optimizer=optimizer)

    # fit network
    history = model.fit(train_X, train_y, epochs=epochs, batch_size=batch_size, validation_data=(test_X, test_y), verbose=verbose, shuffle=False)
    if plotResult:
	    # plot history
	    fig = plot.figure(figsize=(10,8))
	    plot.plot(history.history['loss'], label='train')
	    plot.plot(history.history['val_loss'], label='test')
	    plot.xlabel('Epochs (-)')
	    plot.ylabel('Loss (-)')
	    plot.title('Model Convergence')
	    plot.legend(loc='best')
	    plot.show()
    
    return model

def predict_ML(model, test_X, test_y, n_lags, scaler):
    # Make a prediction for test
    yhat = model.predict(test_X)
    test_X = test_X.reshape((test_X.shape[0], test_X.shape[2] * n_lags))
    # invert scaling for test prediction
    inv_yhat = concatenate((test_X[:, :], yhat), axis=1)
    inv_yhat = scaler.inverse_transform(inv_yhat)
    inv_yhat = inv_yhat[:,-1]
    
    # invert scaling for actual
    test_y = test_y.reshape((len(test_y), 1))
    inv_y = concatenate((test_X[:, :], test_y), axis=1)
    inv_y = scaler.inverse_transform(inv_y)
    inv_y = inv_y[:,-1]
    
    return inv_y, inv_yhat