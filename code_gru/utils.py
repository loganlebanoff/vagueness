import numpy as np
import tensorflow as tf
from tensorflow.contrib.rnn import BasicRNNCell, BasicLSTMCell, GRUCell

FLAGS = tf.app.flags.FLAGS

def create_cell():
    if FLAGS.CELL_TYPE == 'LSTM':
        cell = BasicLSTMCell(num_units=FLAGS.LATENT_SIZE, activation=tf.nn.tanh, state_is_tuple=False)
    elif FLAGS.CELL_TYPE == 'BASIC_RNN':
        cell = BasicRNNCell(num_units=FLAGS.LATENT_SIZE, activation=tf.nn.tanh)
    elif FLAGS.CELL_TYPE == 'GRU':
        cell = GRUCell(num_units=FLAGS.LATENT_SIZE, activation=tf.nn.tanh)
    return cell