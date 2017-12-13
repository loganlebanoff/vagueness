from __future__ import print_function

import numpy as np
import tensorflow as tf
from tensorflow.contrib.rnn import BasicRNNCell, BasicLSTMCell, GRUCell
import sys
from sklearn import metrics
import os, shutil
import param_names

tensorboard_dir = '/home/logan/tensorboard'
FLAGS = tf.app.flags.FLAGS

def create_cell(keep_prob, reuse=False):
    if FLAGS.CELL_TYPE == 'LSTM':
        cell = BasicLSTMCell(num_units=FLAGS.LATENT_SIZE, activation=tf.nn.tanh,
                              state_is_tuple=True, reuse=reuse)
    elif FLAGS.CELL_TYPE == 'BASIC_RNN':
        cell = BasicRNNCell(num_units=FLAGS.LATENT_SIZE, activation=tf.nn.tanh, reuse=reuse)
    elif FLAGS.CELL_TYPE == 'GRU':
        cell = GRUCell(num_units=FLAGS.LATENT_SIZE, activation=tf.nn.tanh, reuse=reuse)
#     cell = tf.contrib.rnn.DropoutWrapper(cell, output_keep_prob=keep_prob, seed=FLAGS.RANDOM_SEED)
    return cell

def gaussian_noise_layer(input_layer, std=1.0):
    noise = tf.random_normal(shape=tf.shape(input_layer), mean=0.0, stddev=std, dtype=tf.float32) 
    return input_layer + noise

def get_variable_by_name(name):
    list = [v for v in tf.global_variables() if v.name == name]
    if len(list) <= 0:
        if name == param_names.GEN_LSTM_WEIGHTS:
            return get_variable_by_name(param_names.ALTERNATIVE_GEN_LSTM_WEIGHTS)
        if name == param_names.GEN_LSTM_BIASES:
            return get_variable_by_name(param_names.ALTERNATIVE_GEN_LSTM_BIASES)
        if name == param_names.TEST_LSTM_WEIGHTS:
            return get_variable_by_name(param_names.ALTERNATIVE_TEST_LSTM_WEIGHTS)
        if name == param_names.TEST_LSTM_BIASES:
            return get_variable_by_name(param_names.ALTERNATIVE_TEST_LSTM_BIASES)
        raise Exception('No variable found by name: ' + name)
    if len(list) > 1:
        raise Exception('Multiple variables found by name: ' + name)
    return list[0]

def eval_variable(name):
    var = get_variable_by_name(name)
    return var.eval()

def print_variable_names():
    for var in tf.trainable_variables():
        print(var.name)

def assign_variable_op(params, pretrained_name, cur_name): #TODO change becuase not using class embedding here
    var = get_variable_by_name(cur_name)
    pretrained_value = params[pretrained_name]
    return var.assign(pretrained_value)

def tf_count(t, val):
    elements_equal_to_value = tf.equal(t, val)
    as_ints = tf.cast(elements_equal_to_value, tf.int32)
    count = tf.reduce_sum(as_ints)
    return count

def variable_summaries(vars):
  """Attach a lot of summaries to a Tensor (for TensorBoard visualization)."""
  with tf.name_scope('summaries'):
      for var in vars:
        mean = tf.reduce_mean(var)
        tf.summary.scalar(var.name + ' mean', mean)
        #     with tf.name_scope('stddev'):
        #       stddev = tf.sqrt(tf.reduce_mean(tf.square(var - mean)))
        #     tf.summary.scalar('stddev ' + var.name, stddev)
        #     tf.summary.scalar('max ' + var.name, tf.reduce_max(var))
        #     tf.summary.scalar('min ' + var.name, tf.reduce_min(var))
        tf.summary.histogram(var.name + ' histogram', var)
        absolute_value = tf.reduce_mean(tf.abs(var))
        tf.summary.scalar(var.name + ' absolute_value', absolute_value)
    
class Metrics:
    def __init__(self, is_binary=False):
        self.metrics_collections = []
        self.averaging_method = 'binary' if is_binary else 'weighted'
        
    def print_and_save_metrics(self, y_true, y_pred, weights=None):
        self.print_metrics(y_true, y_pred, weights)
        self.save_metrics_for_fold(y_true, y_pred, weights)
        
    def save_metrics_for_fold(self, y_true, y_pred, weights=None):
        if weights is None:
            weights = np.ones_like(y_true)
        self.metrics_collections.append( [metrics.accuracy_score(y_true, y_pred, sample_weight=weights),
                metrics.precision_score(y_true, y_pred, average=self.averaging_method, sample_weight=weights),
                metrics.recall_score(y_true, y_pred, average=self.averaging_method, sample_weight=weights),
                metrics.f1_score(y_true, y_pred, average=self.averaging_method, sample_weight=weights)] )
        
    def print_metrics(self, y_true, y_pred, weights=None):
        print ('Performance Metrics\n-------------------\n')
        if weights is None:
            weights = np.ones_like(y_true)
        print ('Accuracy', metrics.accuracy_score(y_true, y_pred, sample_weight=weights))
        print ('')
        report = metrics.classification_report(y_true,y_pred, sample_weight=weights)
        print (report + '\n')
        confusion_matrix = metrics.confusion_matrix(y_true, y_pred, sample_weight=weights)
        print ('Confusion Matrix\n-------------------\n')
        print ('\t\t',end='')
        for i in range(len(confusion_matrix)):
            print (str(i) + '\t',end='')
        print ('\n')
        for i in range(len(confusion_matrix)):
            print (str(i) + '\t\t',end='')
            for j in range(len(confusion_matrix[i])):
                print (str(confusion_matrix[i,j]) + '\t',end='')
            print ('')
    
    def print_metrics_for_all_folds(self):
        if len(self.metrics_collections) == 0:
            raise Exception('No metrics have been saved')
        accuracy, precision, recall, f1 = tuple(np.mean(np.array(self.metrics_collections), axis=0))
        print ('Average Performance on All Folds\n-------------------\n')
        print ('Accuracy', accuracy)
        print ('Precision', precision)
        print ('Recall', recall)
        print ('F1 Score', f1)
        print ('')
        
class Progress_Bar:
    @staticmethod
    def startProgress(title):
        global progress_x
        sys.stdout.write(title + ": [" + "-"*40 + "]" + chr(8)*41)
        sys.stdout.flush()
        progress_x = 0
    @staticmethod
    def progress(x):
        global progress_x
        x = int(x * 40 // 100)
        sys.stdout.write("#" * (x - progress_x))
        sys.stdout.flush()
        progress_x = x
    @staticmethod
    def endProgress():
        sys.stdout.write("#" * (40 - progress_x) + "]\n")
        sys.stdout.flush()
        
def create_leaky_one_hot_table(actually_zero=False):
#     epsilon = 0.0001
    I = np.eye(FLAGS.VOCAB_SIZE)
#     I_excluding_first_row = I[1:,:]     # exclude first row, which is padding
#                                         # we don't want to leak padding because the generator creates
#                                         # perfect one-hot padding at end of sentence
#     
#     # add a small probability for each possible word in training set
#     I_excluding_first_row[I_excluding_first_row == 0] = epsilon
#     I_excluding_first_row[I_excluding_first_row == 0] = 1 - (epsilon * FLAGS.VOCAB_SIZE)

    if actually_zero:
        I[0,:] = 0      # Set PADDING symbol to be [0,0,0,0...], rather than [1,0,0,0...]
    return I
        
def batch_generator(x, y, weights=None, batch_size=64, one_hot=False, actually_zero=False):
    one_hot_table = create_leaky_one_hot_table(actually_zero)
    data_len = x.shape[0]
    for i in range(0, data_len, batch_size):
        x_batch = x[i:min(i+batch_size,data_len)]
        # If giving the discriminator the vocab distribution, then we need to use a 1-hot representation
        if one_hot:
            x_batch = x_batch.astype(float)
            x_batch_transpose = np.transpose(x_batch)
            x_batch_one_hot = one_hot_table[x_batch_transpose.astype(int)]
            x_batch_one_hot_reshaped = x_batch_one_hot.reshape([-1,FLAGS.SEQUENCE_LEN,FLAGS.VOCAB_SIZE])
            x_batch = x_batch_one_hot_reshaped
        y_batch = y[i:min(i+batch_size,data_len)]
        if weights is not None:
            weights_batch = weights[i:min(i+batch_size,data_len)]
            yield x_batch, y_batch, weights_batch, i, data_len
        else:
            yield x_batch, y_batch, i, data_len
            
#         if one_hot:
#             yield x_batch_one_hot_reshaped, y_batch, i, data_len
#         else:
#             yield x_batch, y_batch, i, data_len
        
def create_dirs(dir, num_folds):
    if not os.path.exists(dir):
        os.makedirs(dir)
    for fold_num in range(num_folds):
        fold_dir = dir + '/' + str(fold_num)
        if not os.path.exists(fold_dir):
            os.makedirs(fold_dir)
            
def delete_contents(folder):
    for the_file in os.listdir(folder):
        file_path = os.path.join(folder, the_file)
        try:
            if os.path.isfile(file_path):
                os.unlink(file_path)
            #elif os.path.isdir(file_path): shutil.rmtree(file_path)
        except Exception as e:
            print(e)
            
def clear_tensorboard(name):
    folder = os.path.join(tensorboard_dir, name)
    delete_contents(folder)
        
def get_EOS_idx(samples):
    ''' Used for clipping all words after <eos> word '''
    batch_size = tf.stack([tf.shape(samples)[0],])
    eos = tf.fill(batch_size, 3)
    eos = tf.reshape(eos, [-1, 1])
    d=tf.concat([samples,eos],1)
    EOS_idx=tf.cast(tf.argmax(tf.cast(tf.equal(d, 3), tf.int32), axis=1), tf.int32) + 1
    return EOS_idx
        
        
def softmax(x):
    """Compute softmax values for each sets of scores in x."""
    e_x = np.exp(x - np.max(x))
    return e_x / e_x.sum(axis=0)
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        