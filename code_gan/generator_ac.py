import numpy as np
import tensorflow as tf
from seq2seq import  embedding_rnn_decoder
from tensorflow.contrib.rnn import BasicRNNCell, BasicLSTMCell, GRUCell
import utils
from networkx.algorithms.shortest_paths import weighted

FLAGS = tf.app.flags.FLAGS

def generator(z, c, initial_vague_terms, dims, start_symbol_input, embedding_matrix, keep_prob):
    with tf.variable_scope("G_"):
        cell = utils.create_cell(keep_prob)
#         cell = tf.contrib.rnn.DropoutWrapper(cell, output_keep_prob=0.5)
        
        W = tf.Variable(tf.random_normal([FLAGS.LATENT_SIZE, FLAGS.VOCAB_SIZE]), name='output_weights')    
        b = tf.Variable(tf.random_normal([FLAGS.VOCAB_SIZE]), name='output_biases')    
        
        vague_terms = tf.Variable(initial_vague_terms, dtype=tf.float32, name='vague_terms')
        def create_vague_weights(vague_terms, c):
            a = tf.tile(vague_terms, dims)
            b = tf.reshape(a,[-1,FLAGS.VOCAB_SIZE])
            vague_weights = tf.multiply(b,tf.cast(tf.reshape(c*2 - 2, [-1,1]),tf.float32))
            return vague_weights
        vague_weights = create_vague_weights(vague_terms, c)
        
        outputs, states, samples, probs = embedding_rnn_decoder(start_symbol_input,   # is this ok? I'm not sure what giving 0 inputs does (although it should be completely ignoring inputs)
                                  z,
                                  cell,
                                  FLAGS.VOCAB_SIZE,
                                  FLAGS.EMBEDDING_SIZE,
                                  output_projection=(W,b),
                                  feed_previous=True,
                                  update_embedding_for_previous=True,
                                  sample_from_distribution=FLAGS.SAMPLE,
                                  vague_weights=vague_weights,
                                  embedding_matrix=embedding_matrix,
                                  hidden_noise_std_dev=FLAGS.HIDDEN_NOISE_STD_DEV,
                                  vocab_noise_std_dev=FLAGS.VOCAB_NOISE_STD_DEV)
#                                   class_embedding=c_embedding)

        samples = tf.cast(tf.stack(samples, axis=1), tf.int32)
        probs = tf.stack(probs, axis=1)
        batch_size = tf.stack([tf.shape(c)[0],])
        eos = tf.fill(batch_size, 3)
        eos = tf.reshape(eos, [-1, 1])
        d=tf.concat([samples,eos],1)
        B=tf.cast(tf.argmax(tf.cast(tf.equal(d, 3), tf.int32), axis=1), tf.int32)
        m=tf.sequence_mask(B, tf.shape(samples)[1], dtype=tf.int32)
        samples=tf.multiply(samples,m)
        
        o=tf.reshape(m,[-1,FLAGS.SEQUENCE_LEN,1])
        n = tf.tile(o,[1,1,FLAGS.VOCAB_SIZE])
        u=tf.cast(tf.unstack(n,axis=1),tf.float32)
        
        logits = [tf.matmul(output, W) + b for output in outputs] #TODO add vague vocabulary, and remove class embedding
        weighted_logits = [tf.add(logit, vague_weights) for logit in logits]
        if FLAGS.VOCAB_NOISE_STD_DEV != 0:
          weighted_logits = [utils.gaussian_noise_layer(wl, std=FLAGS.VOCAB_NOISE_STD_DEV) for wl in weighted_logits]
#         x = [tf.nn.softmax(logit) for logit in weighted_logits] # is this softmaxing over the right dimension? this turns into 3D
#                                                                 # and does softmax make sense here in between gen and discr?
        x = [tf.nn.tanh(logit) for logit in weighted_logits]
        for i in range(len(x)):
            x[i] = tf.multiply(x[i], u[i])
        return x, samples, probs, u




























